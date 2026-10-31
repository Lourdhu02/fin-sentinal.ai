from datetime import datetime, timedelta, timezone

import jwt
import pytest

from cli.bootstrap import initialize_system
from config import get_settings
from security.auth import AuthManager
from security.encryption import AESCipher


def test_encryption_authenticates_ciphertext():
    cipher = AESCipher()
    token = cipher.encrypt("private financial text")
    assert cipher.decrypt(token) == "private financial text"
    with pytest.raises(Exception):
        AESCipher("different-key").decrypt(token)


def test_expired_tokens_rejected():
    token = jwt.encode({"sub": "alice", "exp": datetime.now(timezone.utc) - timedelta(seconds=1)},
                       get_settings().jwt_secret, algorithm="HS256")
    with pytest.raises(jwt.ExpiredSignatureError):
        AuthManager().decode_token(token)


def test_bootstrap_never_resets_existing_account():
    initialize_system("admin", "first-password-123")
    with pytest.raises(ValueError, match="already exists"):
        initialize_system("admin", "different-password-123")
