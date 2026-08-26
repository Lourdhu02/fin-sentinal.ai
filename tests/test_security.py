"""Unit tests for AuthManager (JWT + bcrypt) and RBACManager.

Cross-user isolation behaviour is covered separately by the multi-user
harness in tests/test_isolation.py; this module focuses on the primitives:
password hashing, token creation/decoding/expiry/tampering, authentication
against the real SQLite layer, and role-based permission checks.
"""

from __future__ import annotations

import uuid

import jwt as pyjwt
import pytest

from database.db_manager import DatabaseManager
from models.user import User
from security.auth import AuthManager
from security.rbac import RBACManager


def _unique_username(prefix: str = "sec") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def _make_user(username: str, role: str = "user", user_id: int | None = None) -> User:
    return User(
        id=user_id,
        username=username,
        password_hash="not-a-real-hash",
        role=role,  # type: ignore[arg-type]
    )


@pytest.fixture()
def auth() -> AuthManager:
    return AuthManager()


@pytest.fixture()
def db() -> DatabaseManager:
    # Uses the hermetic FINSENTINEL_DB_PATH configured in tests/conftest.py.
    return DatabaseManager()


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------
def test_password_hash_roundtrip(auth: AuthManager):
    hashed = auth.hash_password("hunter2!")
    assert hashed != "hunter2!"
    assert hashed.startswith("$2b$")  # bcrypt identifier
    assert auth.verify_password("hunter2!", hashed)


def test_wrong_password_fails(auth: AuthManager):
    hashed = auth.hash_password("correct horse")
    assert not auth.verify_password("battery staple", hashed)


def test_verify_against_empty_or_garbage_hash_is_false(auth: AuthManager):
    assert auth.verify_password("anything", "") is False
    assert auth.verify_password("anything", "not-a-bcrypt-hash") is False


def test_hashes_are_salted_per_call(auth: AuthManager):
    assert auth.hash_password("same-input") != auth.hash_password("same-input")


# ---------------------------------------------------------------------------
# Token creation / decoding
# ---------------------------------------------------------------------------
def test_token_roundtrip_carries_identity_claims(auth: AuthManager):
    user = _make_user("alice", role="admin", user_id=7)
    token = auth.create_access_token(user)

    payload = auth.decode_token(token)

    assert payload["sub"] == "alice"
    assert payload["user_id"] == 7
    assert payload["role"] == "admin"
    assert payload["exp"] > payload["iat"]


def test_expired_token_is_rejected(auth: AuthManager):
    user = _make_user("bob")
    token = auth.create_access_token(user, expires_minutes=-1)

    with pytest.raises(pyjwt.ExpiredSignatureError):
        auth.decode_token(token)


def test_tampered_token_is_rejected(auth: AuthManager):
    user = _make_user("carol")
    token = auth.create_access_token(user)
    header, body, signature = token.split(".")
    forged = f"{header}.{body}.AAAA{signature[4:]}"

    with pytest.raises(pyjwt.InvalidTokenError):
        auth.decode_token(forged)


def test_token_signed_with_wrong_secret_is_rejected(auth: AuthManager):
    # Settings is a frozen dataclass, so simulate an attacker-signed token by
    # encoding a valid-looking payload with a foreign secret instead of
    # mutating the trusted secret.
    foreign_token = pyjwt.encode(
        {"sub": "dave", "user_id": 9, "role": "admin"},
        "attacker-controlled-secret",
        algorithm="HS256",
    )

    with pytest.raises(pyjwt.InvalidTokenError):
        auth.decode_token(foreign_token)


# ---------------------------------------------------------------------------
# Authentication against SQLite
# ---------------------------------------------------------------------------
def test_authenticate_with_valid_credentials(auth: AuthManager, db: DatabaseManager):
    username = _unique_username()
    db.create_user(username, auth.hash_password("s3cret"), role="user")

    result = auth.authenticate(username, "s3cret", db_manager=db)

    assert result is not None
    assert result["username"] == username
    assert result["role"] == "user"
    assert isinstance(result["id"], int)


def test_authenticate_rejects_bad_password_and_unknown_user(auth: AuthManager, db: DatabaseManager):
    username = _unique_username()
    db.create_user(username, auth.hash_password("s3cret"), role="user")

    assert auth.authenticate(username, "wrong", db_manager=db) is None
    assert auth.authenticate("no_such_user_xyz", "s3cret", db_manager=db) is None


def test_authenticate_rejects_deactivated_user(auth: AuthManager, db: DatabaseManager):
    username = _unique_username()
    created = db.create_user(username, auth.hash_password("s3cret"), role="user")
    db.connection.execute("UPDATE users SET is_active = 0 WHERE id = ?", (created.id,))
    db.connection.commit()

    assert auth.authenticate(username, "s3cret", db_manager=db) is None


def test_authenticate_user_returns_user_model(auth: AuthManager, db: DatabaseManager):
    username = _unique_username()
    db.create_user(username, auth.hash_password("pw123456"), role="admin")

    user = auth.authenticate_user(db, username, "pw123456")

    assert isinstance(user, User)
    assert user.role == "admin"
    assert auth.authenticate_user(db, username, "bad") is None


# ---------------------------------------------------------------------------
# RBAC
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("role", "action", "expected"),
    [
        ("admin", "chat", True),
        ("admin", "create_user", True),
        ("admin", "view_audit", True),
        ("admin", "anything_unlisted", True),  # admin bypass
        ("user", "chat", True),
        ("user", "upload", True),
        ("user", "create_user", False),
        ("user", "view_audit", False),
        ("guest", "chat", False),  # unknown roles get nothing
        ("", "chat", False),
    ],
)
def test_has_permission_matrix(role: str, action: str, expected: bool):
    assert RBACManager().has_permission(role, action) is expected


def test_require_permission_accepts_dict_or_user_model():
    rbac = RBACManager()
    rbac.require_permission({"role": "user"}, "upload")  # dict payloads (JWT claims)
    rbac.require_permission(_make_user("eve", role="admin"), "view_audit")


def test_require_permission_raises_without_user():
    with pytest.raises(PermissionError, match="Authentication required"):
        RBACManager().require_permission(None, "chat")


def test_require_permission_raises_for_missing_permission():
    with pytest.raises(PermissionError, match="cannot perform"):
        RBACManager().require_permission({"role": "user"}, "view_audit")


def test_require_role_membership():
    rbac = RBACManager()
    rbac.require_role({"role": "admin"}, {"admin"})
    rbac.require_role(_make_user("frank", role="user"), {"user", "admin"})
    with pytest.raises(PermissionError, match="Insufficient role"):
        rbac.require_role({"role": "user"}, {"admin"})
    with pytest.raises(PermissionError, match="Authentication required"):
        rbac.require_role(None, {"admin"})
