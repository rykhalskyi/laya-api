import hashlib
import secrets
import sqlite3
from pathlib import Path


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

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.database_path)

    @staticmethod
    def _hash(key: str) -> str:
        return hashlib.sha256(key.encode("utf-8")).hexdigest()

    def create(self, name: str) -> str:
        key = f"laya_{secrets.token_urlsafe(32)}"
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO api_keys (key_hash, name) VALUES (?, ?)",
                (self._hash(key), name),
            )
        return key

    def is_valid(self, key: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM api_keys WHERE key_hash = ? AND revoked_at IS NULL",
                (self._hash(key),),
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