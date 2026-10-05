from __future__ import annotations

import argparse
import getpass
import json
import os
import sys

from config import get_settings
from database.db_manager import DatabaseManager
from database.vector_store import ChromaDBVectorStore
from api.routes.auth import pwd_context


def initialize_system(admin_username: str, admin_password: str, reset_password: bool = False) -> dict:
    settings = get_settings()
    settings.ensure_directories()
    db = DatabaseManager()
    
    existing = db.get_user_by_username(admin_username)
    password_hash = pwd_context.hash(admin_password)
    if existing is None:
        existing = db.create_user(
            username=admin_username,
            password_hash=password_hash,
            role="admin",
        )
    elif reset_password:
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
        "message": "System initialized. Admin token not printed for security."
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Initialize FinSentinelAI")
    parser.add_argument("--admin-username", default="admin")
    parser.add_argument("--reset-admin-password", action="store_true", help="Reset password if user exists")
    args = parser.parse_args()
    
    admin_password = os.environ.get("FINSENTINEL_ADMIN_PASSWORD")
    if not admin_password:
        if not sys.stdin.isatty():
            print("Error: admin password must be provided via FINSENTINEL_ADMIN_PASSWORD env var in non-interactive mode.", file=sys.stderr)
            return 1
        admin_password = getpass.getpass("Enter admin password: ")
        
    if len(admin_password) < 8:
        print("Error: admin password must be at least 8 characters.", file=sys.stderr)
        return 1

    result = initialize_system(args.admin_username, admin_password, args.reset_admin_password)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
