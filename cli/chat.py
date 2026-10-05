from __future__ import annotations

from getpass import getpass

from core.pipeline import FinSentinelPipeline
from database.db_manager import DatabaseManager
from security.auth import AuthManager
from security.rbac import RBACManager


def run_chat(username: str, password: str | None = None) -> int:
    password = password or getpass("Password: ")
    db = DatabaseManager()
    auth = AuthManager()
    user = auth.authenticate_user(db, username, password)
    RBACManager().require_permission(user, "chat")
    pipeline = FinSentinelPipeline(db_manager=db)
    session_id = f"user_{user.id}_default"
    print(f"\nAuthenticated as {user.username} ({user.role})")
    print("Commands: 'exit'/'quit' to end  |  'reset' to clear conversation history\n")
    while True:
        try:
            query = input("finsentinel> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nSession ended.")
            break
        if not query:
            continue
        if query.lower() in {"exit", "quit"}:
            break
        if query.lower() == "reset":
            cleared = pipeline.reset_conversation(session_id)
            print(f"Conversation history cleared ({cleared} turns).")
            continue
        result = pipeline.query(query, session_id=session_id, user_id=user.id)
        print(f"\n{result['response']}\n")
    return 0
