import pytest


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("FINSENTINEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("FINSENTINEL_DB_PATH", str(tmp_path / "test.db"))
    from config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
