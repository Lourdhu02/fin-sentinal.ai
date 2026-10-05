from __future__ import annotations

import base64
import hashlib
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


def _default_secret(name: str) -> str:
    digest = hashlib.sha256(f"finsentinelai::{name}".encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("utf-8")


@dataclass(frozen=True, slots=True)
class Settings:
    base_dir: Path
    data_dir: Path
    db_path: Path
    model_name: str
    embedding_model: str
    encryption_key: str
    jwt_secret: str
    jwt_algorithm: str
    token_expiry_minutes: int

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def encryption_key_bytes(self) -> bytes:
        raw = self.encryption_key.encode("utf-8")
        try:
            decoded = base64.urlsafe_b64decode(raw)
            if len(decoded) == 32:
                return decoded
        except Exception:
            pass
        return hashlib.sha256(raw).digest()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    base_dir = Path(__file__).resolve().parent
    data_dir = Path(os.getenv("FINSENTINEL_DATA_DIR", base_dir / "runtime"))
    db_path = Path(os.getenv("FINSENTINEL_DB_PATH", data_dir / "finsentinel.db"))
    settings = Settings(
        base_dir=base_dir,
        data_dir=data_dir,
        db_path=db_path,
        model_name=os.getenv("FINSENTINEL_MODEL_NAME", "mistral:7b-instruct-q4_K_M"),
        embedding_model=os.getenv("FINSENTINEL_EMBED_MODEL", "all-MiniLM-L6-v2"),
        encryption_key=os.getenv("FINSENTINEL_ENCRYPTION_KEY", _default_secret("encryption")),
        jwt_secret=os.getenv("FINSENTINEL_JWT_SECRET", _default_secret("jwt")),
        jwt_algorithm="HS256",
        token_expiry_minutes=int(os.getenv("FINSENTINEL_TOKEN_EXPIRY_MINUTES", "60")),
    )
    settings.ensure_directories()
    return settings
