from __future__ import annotations

import base64
import hashlib
import os
import secrets
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


def _default_secret(name: str) -> str:
    digest = hashlib.sha256(f"finsentinelai::{name}".encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("utf-8")


def _secret(name: str, data_dir: Path, production: bool) -> str:
    value = os.getenv(f"FINSENTINEL_{name.upper()}")
    if value and not value.startswith("generate_"):
        if production and len(value) < 32:
            raise ValueError(f"FINSENTINEL_{name.upper()} must contain at least 32 characters")
        if value == _default_secret(name.removesuffix("_secret").removesuffix("_key")):
            raise ValueError("Legacy deterministic secrets are not supported")
        return value
    if production:
        raise ValueError(f"FINSENTINEL_{name.upper()} is required in production")
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / f".{name}"
    try:
        with path.open("x", encoding="utf-8") as stream:
            value = secrets.token_urlsafe(48)
            stream.write(value)
        path.chmod(0o600)
        return value
    except FileExistsError:
        value = path.read_text(encoding="utf-8").strip()
        if len(value) < 32:
            raise ValueError(f"Invalid local secret file: {path.name}")
        return value


@dataclass(frozen=True, slots=True)
class Settings:
    base_dir: Path
    data_dir: Path
    db_path: Path
    faiss_index_path: Path
    model_name: str
    embedding_model: str
    encryption_key: str
    jwt_secret: str
    jwt_algorithm: str
    token_expiry_minutes: int
    offline: bool = True
    production: bool = False
    max_upload_bytes: int = 25 * 1024 * 1024
    max_upload_files: int = 10
    max_pdf_pages: int = 200
    registration_enabled: bool = True
    reranker_enabled: bool = True

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.faiss_index_path.parent.mkdir(parents=True, exist_ok=True)

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
    faiss_index_path = Path(os.getenv("FINSENTINEL_FAISS_PATH", data_dir / "vectors.index"))
    production = os.getenv("FINSENTINEL_ENV", "development") == "production"
    settings = Settings(
        base_dir=base_dir,
        data_dir=data_dir,
        db_path=db_path,
        faiss_index_path=faiss_index_path,
        model_name=os.getenv("FINSENTINEL_MODEL_NAME", "mistral:7b-instruct-q4_K_M"),
        embedding_model=os.getenv("FINSENTINEL_EMBED_MODEL", "all-MiniLM-L6-v2"),
        encryption_key=_secret("encryption_key", data_dir, production),
        jwt_secret=_secret("jwt_secret", data_dir, production),
        jwt_algorithm="HS256",
        token_expiry_minutes=int(os.getenv("FINSENTINEL_TOKEN_EXPIRY_MINUTES", "60")),
        offline=os.getenv("FINSENTINEL_OFFLINE", "1") == "1",
        production=production,
        max_upload_bytes=int(os.getenv("FINSENTINEL_MAX_UPLOAD_BYTES", str(25 * 1024 * 1024))),
        max_pdf_pages=int(os.getenv("FINSENTINEL_MAX_PDF_PAGES", "200")),
        registration_enabled=os.getenv("FINSENTINEL_REGISTRATION", "0" if production else "1") == "1",
        reranker_enabled=os.getenv("FINSENTINEL_RERANKER", "1") == "1",
    )
    if min(settings.token_expiry_minutes, settings.max_upload_bytes, settings.max_pdf_pages) <= 0:
        raise ValueError("Expiry and resource limits must be positive")
    settings.ensure_directories()
    return settings
