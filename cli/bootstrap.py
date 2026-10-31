from __future__ import annotations

import argparse
import json

from config import get_settings
from database.db_manager import DatabaseManager
from database.vector_store import ChromaDBVectorStore
from security.auth import AuthManager


def initialize_system(admin_username: str, admin_password: str) -> dict:
    settings = get_settings()
    settings.ensure_directories()
    db = DatabaseManager()
    auth = AuthManager()
    existing_record = db.get_user(admin_username)
    existing = db.get_user_by_username(admin_username)
    password_hash = auth.hash_password(admin_password)
    if existing is None:
        existing = db.create_user(
            username=admin_username,
            password_hash=password_hash,
            role="admin",
        )
    elif existing_record is not None and not auth.verify_password(admin_password, existing_record["password_hash"]):
        db.connection.execute(
            "UPDATE users SET password_hash = ?, role = ? WHERE username = ?",
            (password_hash, "admin", admin_username),
        )
        db.connection.commit()
        existing = db.get_user_by_username(admin_username)
    vector_store = ChromaDBVectorStore()
    return {
        "db_path": str(settings.db_path),
        "chroma_dir": str(settings.data_dir / "chroma"),
        "admin_username": existing.username,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Initialize FinSentinelAI")
    parser.add_argument("--admin-username", default="admin")
    parser.add_argument("--admin-password")
    args = parser.parse_args()
    from getpass import getpass
    result = initialize_system(args.admin_username, args.admin_password or getpass("Admin password: "))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
