from fastapi.testclient import TestClient

from api.main import create_app


def test_health_does_not_load_models():
    with TestClient(create_app()) as client:
        assert client.get("/api/health").status_code == 200
        assert client.app.state.container.pipeline is None
        assert client.get("/api/documents/list").status_code == 401
