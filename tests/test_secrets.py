import pytest

from config import get_settings


def test_local_secrets_persist_but_are_not_deterministic(tmp_path):
    first = get_settings().jwt_secret
    get_settings.cache_clear()
    assert get_settings().jwt_secret == first
    assert len(first) >= 32


def test_production_requires_secrets(monkeypatch):
    monkeypatch.setenv("FINSENTINEL_ENV", "production")
    monkeypatch.delenv("FINSENTINEL_JWT_SECRET", raising=False)
    monkeypatch.delenv("FINSENTINEL_ENCRYPTION_KEY", raising=False)
    with pytest.raises(ValueError, match="required"):
        get_settings()
