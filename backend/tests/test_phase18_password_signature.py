"""Phase 18: change-password endpoint + signature upload/download."""

import io
import struct
import zlib

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import *  # noqa: F401,F403
from app.services.seed import DEFAULT_ADMIN_EMAIL, DEFAULT_ADMIN_PASSWORD, run_seed


def _tiny_png() -> bytes:
    """1x1 transparent PNG — smallest valid PNG."""
    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0))
    idat = chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00\x00"))
    iend = chunk(b"IEND", b"")
    return sig + ihdr + idat + iend


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "p18.db"
    storage_dir = tmp_path / "storage"
    storage_dir.mkdir()
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("STORAGE_LOCAL_PATH", str(storage_dir))

    engine = create_engine(f"sqlite:///{db_path}", future=True)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    from app.db import session as session_mod
    import app.services.seed as seed_mod

    orig = session_mod.SessionLocal
    orig_seed = seed_mod.SessionLocal
    session_mod.SessionLocal = TestingSessionLocal
    seed_mod.SessionLocal = TestingSessionLocal
    try:
        run_seed()
        yield TestClient(app)
    finally:
        session_mod.SessionLocal = orig
        seed_mod.SessionLocal = orig_seed
        app.dependency_overrides.clear()


def _login(client: TestClient, email: str = DEFAULT_ADMIN_EMAIL, password: str = DEFAULT_ADMIN_PASSWORD) -> dict[str, str]:
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_change_password_rejects_wrong_current(client: TestClient) -> None:
    h = _login(client)
    r = client.post(
        "/api/v1/auth/change-password",
        headers=h,
        json={"current_password": "wrong", "new_password": "Newer@1234"},
    )
    assert r.status_code == 400
    assert "current password" in r.json()["detail"].lower()


def test_change_password_rejects_same_password(client: TestClient) -> None:
    h = _login(client)
    r = client.post(
        "/api/v1/auth/change-password",
        headers=h,
        json={
            "current_password": DEFAULT_ADMIN_PASSWORD,
            "new_password": DEFAULT_ADMIN_PASSWORD,
        },
    )
    assert r.status_code == 400
    assert "different" in r.json()["detail"].lower()


def test_change_password_rejects_too_short(client: TestClient) -> None:
    h = _login(client)
    r = client.post(
        "/api/v1/auth/change-password",
        headers=h,
        json={"current_password": DEFAULT_ADMIN_PASSWORD, "new_password": "short"},
    )
    assert r.status_code == 422


def test_change_password_happy_path(client: TestClient) -> None:
    h = _login(client)
    new_pw = "BrandNew@2026"
    r = client.post(
        "/api/v1/auth/change-password",
        headers=h,
        json={"current_password": DEFAULT_ADMIN_PASSWORD, "new_password": new_pw},
    )
    assert r.status_code == 200
    # Old password should now fail
    r = client.post(
        "/api/v1/auth/login",
        json={"email": DEFAULT_ADMIN_EMAIL, "password": DEFAULT_ADMIN_PASSWORD},
    )
    assert r.status_code == 401
    # New password should work
    r = client.post(
        "/api/v1/auth/login",
        json={"email": DEFAULT_ADMIN_EMAIL, "password": new_pw},
    )
    assert r.status_code == 200


def test_signature_upload_get_delete_round_trip(client: TestClient) -> None:
    h = _login(client)
    png = _tiny_png()

    # No signature yet
    assert client.get("/api/v1/auth/me/signature", headers=h).status_code == 404
    assert client.get("/api/v1/auth/me", headers=h).json()["has_signature"] is False

    # Upload
    r = client.post(
        "/api/v1/auth/me/signature",
        headers=h,
        files={"file": ("sig.png", io.BytesIO(png), "image/png")},
    )
    assert r.status_code == 200, r.text
    assert r.json()["signature_path"].startswith("signatures/")
    assert r.json()["size_bytes"] == len(png)

    # GET returns the same bytes
    r = client.get("/api/v1/auth/me/signature", headers=h)
    assert r.status_code == 200
    assert r.content == png

    # /me reflects the change
    assert client.get("/api/v1/auth/me", headers=h).json()["has_signature"] is True

    # Delete
    r = client.delete("/api/v1/auth/me/signature", headers=h)
    assert r.status_code == 204
    assert client.get("/api/v1/auth/me/signature", headers=h).status_code == 404
    assert client.get("/api/v1/auth/me", headers=h).json()["has_signature"] is False


def test_signature_upload_rejects_non_image(client: TestClient) -> None:
    h = _login(client)
    r = client.post(
        "/api/v1/auth/me/signature",
        headers=h,
        files={"file": ("notes.txt", io.BytesIO(b"not an image"), "text/plain")},
    )
    assert r.status_code == 400


def test_change_password_requires_auth(client: TestClient) -> None:
    r = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "x", "new_password": "Newer@1234"},
    )
    assert r.status_code == 401


def test_signature_endpoints_require_auth(client: TestClient) -> None:
    assert client.get("/api/v1/auth/me/signature").status_code == 401
    assert client.post(
        "/api/v1/auth/me/signature",
        files={"file": ("x.png", io.BytesIO(b""), "image/png")},
    ).status_code == 401
    assert client.delete("/api/v1/auth/me/signature").status_code == 401
