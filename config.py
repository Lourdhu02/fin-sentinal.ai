from __future__ import annotations

import base64
import hashlib
import os
import secrets
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


def _get_dev_secret(data_dir: Path, name: str) -> str:
    """Generate and store dev secrets to <data_dir>/.secrets. ONLY for FINSENTINEL_ENV=dev."""
    secrets_file = data_dir / ".secrets"
    if secrets_file.exists():
        with open(secrets_file, "r") as f:
            for line in f:
                if line.startswith(f"{name}="):
                    return line.strip().split("=", 1)[1]
    
    # Generate new
    new_secret = secrets.token_urlsafe(32)
    with open(secrets_file, "a") as f:
        f.write(f"{name}={new_secret}\n")
    os.chmod(secrets_file, 0o600)
    return new_secret


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
    open_registration: bool
    max_upload_size: int

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
    data_dir.mkdir(parents=True, exist_ok=True)
    
    env = os.getenv("FINSENTINEL_ENV", "prod")
    
    enc_key = os.getenv("FINSENTINEL_ENCRYPTION_KEY")
    jwt_sec = os.getenv("FINSENTINEL_JWT_SECRET")
    
    if env == "dev" or env == "test":
        enc_key = enc_key or _get_dev_secret(data_dir, "encryption")
        jwt_sec = jwt_sec or _get_dev_secret(data_dir, "jwt")
    
    if not enc_key or len(enc_key) < 32:
        raise ValueError("FINSENTINEL_ENCRYPTION_KEY must be set with at least 32 bytes in prod (see rotation docs).")
    if not jwt_sec or len(jwt_sec) < 32:
        raise ValueError("FINSENTINEL_JWT_SECRET must be set with at least 32 bytes in prod (see rotation docs).")
        
    db_path = Path(os.getenv("FINSENTINEL_DB_PATH", data_dir / "finsentinel.db"))
    settings = Settings(
        base_dir=base_dir,
        data_dir=data_dir,
        db_path=db_path,
        model_name=os.getenv("FINSENTINEL_MODEL_NAME", "mistral:7b-instruct-q4_K_M"),
        embedding_model=os.getenv("FINSENTINEL_EMBED_MODEL", "all-MiniLM-L6-v2"),
        encryption_key=enc_key,
        jwt_secret=jwt_sec,
        jwt_algorithm="HS256",
        token_expiry_minutes=int(os.getenv("FINSENTINEL_TOKEN_EXPIRY_MINUTES", "60")),
        open_registration=os.getenv("FINSENTINEL_OPEN_REGISTRATION", "true").lower() == "true",
        max_upload_size=int(os.getenv("FINSENTINEL_MAX_UPLOAD_SIZE", str(20 * 1024 * 1024))),
    )
    settings.ensure_directories()
    return settings
