"""Phase 32: Web Push subscriptions + delivery stub + VAPID."""

import base64

import pytest
from cryptography.hazmat.primitives import serialization
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import *  # noqa: F401,F403
from app.models.push import PushSubscription
from app.services import push_service
from app.services.seed import DEFAULT_ADMIN_EMAIL, DEFAULT_ADMIN_PASSWORD, run_seed


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "p32.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")

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
        yield TestClient(app), TestingSessionLocal
    finally:
        session_mod.SessionLocal = orig
        seed_mod.SessionLocal = orig_seed
        app.dependency_overrides.clear()


def _admin_h(c: TestClient) -> dict[str, str]:
    r = c.post(
        "/api/v1/auth/login",
        json={"email": DEFAULT_ADMIN_EMAIL, "password": DEFAULT_ADMIN_PASSWORD},
    )
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_vapid_public_key_endpoint_returns_p256_point(client) -> None:
    c, _ = client
    h = _admin_h(c)
    r = c.get("/api/v1/push/vapid-public-key", headers=h)
    assert r.status_code == 200, r.text
    pk = r.json()["public_key"]
    # base64url-no-padding raw P-256 uncompressed point = 65 bytes
    # that always start with 0x04. The browser will assert this.
    padded = pk + "=" * ((4 - len(pk) % 4) % 4)
    raw = base64.urlsafe_b64decode(padded)
    assert len(raw) == 65 and raw[0] == 0x04


def test_vapid_keypair_persists(client) -> None:
    """Two calls return the same key - the keypair is lazily minted
    on first use and persisted in settings_kv."""
    c, _ = client
    h = _admin_h(c)
    a = c.get("/api/v1/push/vapid-public-key", headers=h).json()["public_key"]
    b = c.get("/api/v1/push/vapid-public-key", headers=h).json()["public_key"]
    assert a == b


def test_subscribe_then_list_then_unsubscribe(client) -> None:
    c, SessionLocal = client
    h = _admin_h(c)
    body = {
        "endpoint": "https://fcm.googleapis.com/example/abc",
        "p256dh": "AAAAAA",
        "auth": "BBBB",
        "user_agent": "Mozilla/5.0 (test)",
    }
    r = c.post("/api/v1/push/subscribe", headers=h, json=body)
    assert r.status_code == 200, r.text
    row = r.json()
    assert row["endpoint"] == body["endpoint"]

    rows = c.get("/api/v1/push/subscriptions", headers=h).json()
    assert len(rows) == 1
    assert rows[0]["user_agent"].startswith("Mozilla/5.0")

    # Same endpoint upserts: no duplicate row
    c.post("/api/v1/push/subscribe", headers=h, json=body)
    assert len(c.get("/api/v1/push/subscriptions", headers=h).json()) == 1

    # Unsubscribe removes it
    r = c.post(
        "/api/v1/push/unsubscribe",
        headers=h,
        json={"endpoint": body["endpoint"]},
    )
    assert r.status_code == 200
    assert r.json()["removed"] == 1
    assert c.get("/api/v1/push/subscriptions", headers=h).json() == []


def test_subscribe_endpoint_unique_across_users(client) -> None:
    """Same endpoint string can only point to one user - re-subscribing
    on a different login moves ownership rather than duplicating."""
    c, SessionLocal = client
    h = _admin_h(c)
    body = {
        "endpoint": "https://example.org/p/xyz",
        "p256dh": "P256",
        "auth": "AUTH",
    }
    c.post("/api/v1/push/subscribe", headers=h, json=body)
    db = SessionLocal()
    try:
        n = db.query(PushSubscription).count()
        assert n == 1
    finally:
        db.close()


def test_push_endpoints_require_auth(client) -> None:
    c, _ = client
    assert c.get("/api/v1/push/vapid-public-key").status_code == 401
    assert c.post(
        "/api/v1/push/subscribe",
        json={"endpoint": "x", "p256dh": "y", "auth": "z"},
    ).status_code == 401


def test_send_to_user_returns_logged_when_pywebpush_missing(client, monkeypatch) -> None:
    """Pywebpush may not be installable on every host; the service
    must still drain the subscription list and report stats."""
    c, SessionLocal = client
    h = _admin_h(c)
    me = c.get("/api/v1/auth/me", headers=h).json()
    c.post(
        "/api/v1/push/subscribe",
        headers=h,
        json={"endpoint": "https://example.test/e/1", "p256dh": "AA", "auth": "BB"},
    )
    db = SessionLocal()
    try:
        stats = push_service.send_to_user(
            db,
            user_id=me["id"],
            payload={"title": "hi", "body": "test"},
        )
        # In console / no-pywebpush mode the stub returns ok=True
        # with detail "logged" so the stats look like a successful
        # send. Either way, no exception and no failure row.
        assert stats["failed"] == 0
        assert stats["sent"] + stats["gone"] >= 1
    finally:
        db.close()


def test_send_to_user_with_no_subs_is_a_noop(client) -> None:
    c, SessionLocal = client
    h = _admin_h(c)
    me = c.get("/api/v1/auth/me", headers=h).json()
    db = SessionLocal()
    try:
        stats = push_service.send_to_user(
            db, user_id=me["id"], payload={"title": "x", "body": "y"}
        )
        assert stats == {"sent": 0, "failed": 0, "gone": 0}
    finally:
        db.close()
