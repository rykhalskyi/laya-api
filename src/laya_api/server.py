import hashlib
import logging
import os
import secrets
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader
from pydantic import BaseModel

from laya import Router

from .auth import ApiKeyStore
from .ratelimit import SlidingWindowLimiter

logging.basicConfig(
    level=os.getenv("LAYA_LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("laya_api")


class PredictRequest(BaseModel):
    state: dict[str, Any]
    questions: dict[str, Any]
    model: str | None = None


class ApiKeyRequest(BaseModel):
    name: str


class RevokeApiKeyRequest(BaseModel):
    api_key: str


router = Router(preload=True)
app = FastAPI(title="Laya API")
api_keys = ApiKeyStore(os.getenv("LAYA_API_KEY_DATABASE", "./data/api_keys.db"))
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

RATE_LIMIT_WINDOW = float(os.getenv("LAYA_RATE_LIMIT_WINDOW", "60"))
admin_limiter = SlidingWindowLimiter(int(os.getenv("LAYA_RATE_LIMIT_ADMIN", "10")), RATE_LIMIT_WINDOW)
predict_limiter = SlidingWindowLimiter(int(os.getenv("LAYA_RATE_LIMIT_PREDICT", "120")), RATE_LIMIT_WINDOW)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("CF-Connecting-IP")
    if forwarded:
        return forwarded
    return request.client.host if request.client else "unknown"


def _fingerprint(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:8]


def _key_ttl_days() -> int | None:
    raw = os.getenv("LAYA_KEY_TTL_DAYS", "90").strip().lower()
    if raw in {"", "none", "null"}:
        return None
    return int(raw)


def _rate_limit(limiter: SlidingWindowLimiter, scope: str):
    def dependency(request: Request) -> None:
        client_ip = _client_ip(request)
        retry_after = limiter.check(client_ip)
        if retry_after is not None:
            logger.warning("rate_limit_exceeded scope=%s client_ip=%s", scope, client_ip)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded",
                headers={"Retry-After": str(int(retry_after) + 1)},
            )

    return dependency


admin_rate_limit = _rate_limit(admin_limiter, "admin")
predict_rate_limit = _rate_limit(predict_limiter, "predict")


def require_api_key(
    request: Request,
    api_key: str | None = Security(api_key_header),
) -> str:
    if api_key is None or not api_keys.is_valid(api_key):
        logger.warning(
            "auth_failed scope=predict client_ip=%s key=%s",
            _client_ip(request),
            _fingerprint(api_key) if api_key else "none",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid API key",
        )
    return api_key


def require_admin_key(
    request: Request,
    api_key: str | None = Security(api_key_header),
) -> str:
    admin_key = os.getenv("LAYA_ADMIN_KEY")
    if not admin_key or not api_key or not secrets.compare_digest(api_key, admin_key):
        logger.warning(
            "auth_failed scope=admin client_ip=%s key=%s",
            _client_ip(request),
            _fingerprint(api_key) if api_key else "none",
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin API key required",
        )
    return api_key


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/predict", dependencies=[Depends(predict_rate_limit)])
def predict(request: PredictRequest, _: str = Depends(require_api_key)) -> Any:
    if request.model is None:
        return router.predict(request.state, request.questions)
    return router.predict(request.state, request.questions, model=request.model)


@app.post("/admin/keys", status_code=status.HTTP_201_CREATED, dependencies=[Depends(admin_rate_limit)])
def create_api_key(
    request: ApiKeyRequest,
    http_request: Request,
    _: str = Depends(require_admin_key),
) -> dict[str, str]:
    key = api_keys.create(request.name, ttl_days=_key_ttl_days())
    logger.info(
        "api_key_created name=%s client_ip=%s key=%s",
        request.name,
        _client_ip(http_request),
        _fingerprint(key),
    )
    return {"api_key": key, "name": request.name}


@app.post("/admin/keys/revoke", dependencies=[Depends(admin_rate_limit)])
def revoke_api_key(
    request: RevokeApiKeyRequest,
    http_request: Request,
    _: str = Depends(require_admin_key),
) -> dict[str, bool]:
    client_ip = _client_ip(http_request)
    fingerprint = _fingerprint(request.api_key)
    if not api_keys.revoke(request.api_key):
        logger.warning("api_key_revoke_failed client_ip=%s key=%s", client_ip, fingerprint)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
    logger.info("api_key_revoked client_ip=%s key=%s", client_ip, fingerprint)
    return {"revoked": True}


def run() -> None:
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
