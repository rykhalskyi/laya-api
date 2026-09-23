import os
import secrets
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Security, status
from fastapi.security import APIKeyHeader
from pydantic import BaseModel

from laya import Router

from .auth import ApiKeyStore


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


def require_api_key(api_key: str | None = Security(api_key_header)) -> str:
    if api_key is None or not api_keys.is_valid(api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid API key",
        )
    return api_key


def require_admin_key(api_key: str | None = Security(api_key_header)) -> str:
    admin_key = os.getenv("LAYA_ADMIN_KEY")
    if not admin_key or not api_key or not secrets.compare_digest(api_key, admin_key):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin API key required",
        )
    return api_key


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/predict")
def predict(request: PredictRequest, _: str = Depends(require_api_key)) -> Any:
    if request.model is None:
        return router.predict(request.state, request.questions)
    return router.predict(request.state, request.questions, model=request.model)


@app.post("/admin/keys", status_code=status.HTTP_201_CREATED)
def create_api_key(request: ApiKeyRequest, _: str = Depends(require_admin_key)) -> dict[str, str]:
    return {"api_key": api_keys.create(request.name), "name": request.name}


@app.post("/admin/keys/revoke")
def revoke_api_key(request: RevokeApiKeyRequest, _: str = Depends(require_admin_key)) -> dict[str, bool]:
    if not api_keys.revoke(request.api_key):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
    return {"revoked": True}


def run() -> None:
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
