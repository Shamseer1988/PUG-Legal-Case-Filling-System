"""Phase 26: stream-ticket issuance + SSE-based notification stream."""

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.security import create_stream_ticket, decode_token
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import *  # noqa: F401,F403
from app.models.notification import Notification
from app.services.seed import DEFAULT_ADMIN_EMAIL, DEFAULT_ADMIN_PASSWORD, run_seed


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "p26.db"
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


def _parse_sse(body: str) -> list[tuple[str | None, str]]:
    """Return (event_name, raw_data) pairs from an SSE response body.
    Comment lines (``: keepalive``) are dropped."""
    events: list[tuple[str | None, str]] = []
    cur_event: str | None = None
    cur_data: list[str] = []
    for line in body.splitlines():
        if line.startswith(": "):
            continue
        if line == "":
            if cur_data or cur_event:
                events.append((cur_event, "\n".join(cur_data)))
            cur_event = None
            cur_data = []
            continue
        if line.startswith("event: "):
            cur_event = line[len("event: ") :]
        elif line.startswith("data: "):
            cur_data.append(line[len("data: ") :])
    if cur_data or cur_event:
        events.append((cur_event, "\n".join(cur_data)))
    return events


def test_stream_ticket_is_short_lived_and_typed(client) -> None:
    c, _ = client
    h = _admin_h(c)
    r = c.post("/api/v1/auth/stream-ticket", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ttl_seconds"] == 60
    payload = decode_token(body["ticket"])
    assert payload["type"] == "stream"
    assert payload["sub"]


def test_stream_ticket_requires_auth(client) -> None:
    c, _ = client
    assert c.post("/api/v1/auth/stream-ticket").status_code == 401


def test_stream_endpoint_rejects_missing_or_invalid_ticket(client) -> None:
    c, _ = client
    # No ticket at all - FastAPI returns 422 for missing required query param
    r = c.get("/api/v1/notifications/stream")
    assert r.status_code == 422

    # Garbage ticket -> 401
    r = c.get("/api/v1/notifications/stream?ticket=not-a-jwt")
    assert r.status_code == 401


def test_stream_endpoint_rejects_wrong_token_type(client) -> None:
    """Re-using the bearer access token as a stream ticket must be
    refused - the ticket has its own ``type=stream`` claim."""
    c, _ = client
    h = _admin_h(c)
    bearer = h["Authorization"].removeprefix("Bearer ")
    r = c.get(f"/api/v1/notifications/stream?ticket={bearer}")
    assert r.status_code == 401


def test_stream_emits_hello_then_notification(client, monkeypatch) -> None:
    """Connect first, then drop a Notification row mid-stream, and
    verify the SSE pipeline emits the matching event."""
    import threading
    import time

    import app.api.v1.notifications as nots_mod

    # Snappy polling so the test doesn't take seconds; lifetime
    # long enough that the worker has at least one poll cycle
    # AFTER the new row lands.
    monkeypatch.setattr(nots_mod, "SSE_POLL_SECONDS", 0)
    monkeypatch.setattr(nots_mod, "SSE_MAX_LIFETIME_SECONDS", 2)

    c, SessionLocal = client
    h = _admin_h(c)
    me = c.get("/api/v1/auth/me", headers=h).json()
    user_id = me["id"]

    def insert_after_delay() -> None:
        time.sleep(0.1)
        db = SessionLocal()
        try:
            db.add(
                Notification(
                    user_id=user_id,
                    title="Test event",
                    body="hello",
                    link="/cases/1",
                    event="case.test",
                    related_case_id=None,
                )
            )
            db.commit()
        finally:
            db.close()

    inserter = threading.Thread(target=insert_after_delay, daemon=True)
    inserter.start()

    ticket = create_stream_ticket(user_id, ttl_seconds=60)
    with c.stream("GET", f"/api/v1/notifications/stream?ticket={ticket}") as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        body = "".join(chunk for chunk in r.iter_text())
    inserter.join(timeout=2)

    events = _parse_sse(body)
    event_names = [e[0] for e in events]
    assert "hello" in event_names, f"hello missing from {event_names}"
    assert "notification" in event_names, f"notification missing from {event_names}"

    # The notification payload is a NotificationRead-shaped JSON blob.
    note = next(json.loads(d) for ev, d in events if ev == "notification")
    assert note["title"] == "Test event"
    assert note["body"] == "hello"
    assert note["is_read"] is False


def test_stream_emits_bye_on_max_lifetime(client, monkeypatch) -> None:
    import app.api.v1.notifications as nots_mod

    monkeypatch.setattr(nots_mod, "SSE_POLL_SECONDS", 0)
    monkeypatch.setattr(nots_mod, "SSE_MAX_LIFETIME_SECONDS", 0)

    c, _ = client
    h = _admin_h(c)
    me = c.get("/api/v1/auth/me", headers=h).json()
    ticket = create_stream_ticket(me["id"], ttl_seconds=60)
    with c.stream("GET", f"/api/v1/notifications/stream?ticket={ticket}") as r:
        body = "".join(chunk for chunk in r.iter_text())
    events = _parse_sse(body)
    assert any(ev == "bye" for ev, _ in events)
