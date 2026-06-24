"""Smoke tests for the health endpoints."""

from fastapi.testclient import TestClient

from app.main import app


def test_root() -> None:
    client = TestClient(app)
    r = client.get("/")
    assert r.status_code == 200
    data = r.json()
    assert data["app"]
    assert data["version"]


def test_health() -> None:
    client = TestClient(app)
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
