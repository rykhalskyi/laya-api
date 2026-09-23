import hashlib
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime(TIMESTAMP_FORMAT)


class ApiKeyStore:
    def __init__(self, database_path: str) -> None:
        self.database_path = database_path
        Path(database_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS api_keys (
                    key_hash TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    revoked_at TEXT
                )
                """
            )
            self._migrate(connection)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.database_path)

    @staticmethod
    def _migrate(connection: sqlite3.Connection) -> None:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(api_keys)")}
        if "expires_at" not in columns:
            connection.execute("ALTER TABLE api_keys ADD COLUMN expires_at TEXT")

    @staticmethod
    def _hash(key: str) -> str:
        return hashlib.sha256(key.encode("utf-8")).hexdigest()

    def create(self, name: str, ttl_days: int | None = 90) -> str:
        key = f"laya_{secrets.token_urlsafe(32)}"
        expires_at = None
        if ttl_days is not None:
            expires_at = (datetime.now(timezone.utc) + timedelta(days=ttl_days)).strftime(TIMESTAMP_FORMAT)
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO api_keys (key_hash, name, expires_at) VALUES (?, ?, ?)",
                (self._hash(key), name, expires_at),
            )
        return key

    def is_valid(self, key: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT 1 FROM api_keys
                WHERE key_hash = ?
                AND revoked_at IS NULL
                AND (expires_at IS NULL OR expires_at > ?)
                """,
                (self._hash(key), _utcnow()),
            ).fetchone()
        return row is not None

    def revoke(self, key: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE api_keys
                SET revoked_at = CURRENT_TIMESTAMP
                WHERE key_hash = ? AND revoked_at IS NULL
                """,
                (self._hash(key),),
            )
        return cursor.rowcount == 1