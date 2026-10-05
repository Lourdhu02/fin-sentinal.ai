import pytest
from fastapi.testclient import TestClient
from api.main import app

@pytest.fixture
def client():
    return TestClient(app)

def test_health_check(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}

def test_user_flow(client):
    # Register
    res = client.post("/api/auth/register", json={"username": "testuser", "password": "password123"})
    assert res.status_code == 200
    assert res.json()["username"] == "testuser"

    # Login
    res = client.post("/api/auth/login", data={"username": "testuser", "password": "password123"})
    assert res.status_code == 200
    token = res.json()["access_token"]
    
    headers = {"Authorization": f"Bearer {token}"}

    # Me
    res = client.get("/api/auth/me", headers=headers)
    assert res.status_code == 200
    assert res.json()["username"] == "testuser"

    # Upload
    files = {"files": ("test.txt", b"Hello, World!", "text/plain")}
    res = client.post("/api/documents/upload", headers=headers, files=files)
    assert res.status_code == 200
    
    # List
    res = client.get("/api/documents/list", headers=headers)
    assert res.status_code == 200

    # Chat
    res = client.post("/api/chat/", headers=headers, json={"query": "Hello"})
    assert res.status_code == 200
    assert "response" in res.json()

    # Delete
    res = client.delete("/api/documents/test.txt", headers=headers)
    assert res.status_code == 200
