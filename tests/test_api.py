from fastapi.testclient import TestClient

from api.main import create_app


def test_health_does_not_load_models():
    with TestClient(create_app()) as client:
        assert client.get("/api/health").status_code == 200
        assert client.app.state.container.pipeline is None
        assert client.get("/api/documents/list").status_code == 401


def test_register_login_and_inactive_user():
    with TestClient(create_app()) as client:
        credentials = {"username": "alice", "password": "correct-horse-123"}
        assert client.post("/api/auth/register", json=credentials).status_code == 200
        response = client.post("/api/auth/login", data=credentials)
        assert response.status_code == 200
        headers = {"Authorization": "Bearer " + response.json()["access_token"]}
        assert client.get("/api/auth/me", headers=headers).json()["username"] == "alice"
        db = client.app.state.container.db
        db.connection.execute("UPDATE users SET is_active = 0")
        db.connection.commit()
        assert client.get("/api/auth/me", headers=headers).status_code == 401
        assert client.post("/api/auth/login", data=credentials).status_code == 400


def test_registration_policy_and_validation(monkeypatch):
    with TestClient(create_app()) as client:
        assert client.post("/api/auth/register", json={"username": "a", "password": "x"}).status_code == 422
    monkeypatch.setenv("FINSENTINEL_REGISTRATION", "0")
    from config import get_settings
    get_settings.cache_clear()
    with TestClient(create_app()) as client:
        assert client.post("/api/auth/register", json={"username": "alice", "password": "long-password-123"}).status_code == 403
