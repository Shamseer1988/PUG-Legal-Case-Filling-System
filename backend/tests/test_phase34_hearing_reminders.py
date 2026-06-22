"""Phase 34: scheduled hearing reminders (24h + 1h windows)."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import *  # noqa: F401,F403
from app.models.case import Case
from app.models.court import Hearing
from app.models.notification import Notification
from app.services import hearing_reminder_service
from app.services.seed import DEFAULT_ADMIN_EMAIL, DEFAULT_ADMIN_PASSWORD, run_seed


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "p34.db"
    storage_dir = tmp_path / "storage"
    storage_dir.mkdir()
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("STORAGE_LOCAL_PATH", str(storage_dir))
    monkeypatch.delenv("SMTP_HOST", raising=False)

    engine = create_engine(f"sqlite:///{db_path}", future=True)
    TestingSessionLocal = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, future=True
    )
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


def _make_case_with_hearing(
    c: TestClient,
    h: dict[str, str],
    SessionLocal,
    *,
    hearing_in: timedelta,
) -> tuple[int, int]:
    """Returns (case_id, hearing_id). Hearing is scheduled at now+hearing_in."""
    divs = c.get("/api/v1/masters/divisions", headers=h).json()
    div_id = divs[0]["id"]
    banks = c.get("/api/v1/masters/banks", headers=h).json()
    cust = c.post(
        "/api/v1/masters/customers",
        headers=h,
        json={"code": "HR1", "name": "Hearing Co", "division_id": div_id},
    ).json()
    me = c.get("/api/v1/auth/me", headers=h).json()
    case = c.post(
        "/api/v1/cases",
        headers=h,
        json={
            "customer_id": cust["id"],
            "division_id": div_id,
            "is_civil": True,
            "auditor_id": me["id"],
            "cheques": [
                {
                    "cheque_number": "CH-HR-1",
                    "bank_id": banks[0]["id"],
                    "amount": "200.00",
                    "cheque_date": "2026-05-15",
                    "cheque_type": "Normal",
                    "bounce_reason": "Funds",
                },
            ],
        },
    ).json()
    case_id = case["id"]

    # Skip the workflow dance — drop a Hearing row in directly with
    # the test-supplied schedule. The scanner doesn't care how the
    # row got there.
    db = SessionLocal()
    try:
        hearing = Hearing(
            case_id=case_id,
            hearing_date=datetime.now(timezone.utc) + hearing_in,
            hearing_type="First Hearing",
            location="Court Room 5",
            recorded_by_id=me["id"],
        )
        db.add(hearing)
        db.commit()
        hearing_id = hearing.id
    finally:
        db.close()
    return case_id, hearing_id


def test_no_reminders_when_hearing_is_far_in_future(client) -> None:
    c, SessionLocal = client
    h = _admin_h(c)
    _make_case_with_hearing(c, h, SessionLocal, hearing_in=timedelta(days=7))
    db = SessionLocal()
    try:
        stats = hearing_reminder_service.scan_and_notify(db)
        assert stats["sent_24h"] == 0
        assert stats["sent_1h"] == 0
    finally:
        db.close()


def test_24h_window_fires_once(client) -> None:
    c, SessionLocal = client
    h = _admin_h(c)
    _make_case_with_hearing(c, h, SessionLocal, hearing_in=timedelta(hours=20))
    db = SessionLocal()
    try:
        first = hearing_reminder_service.scan_and_notify(db)
        assert first["sent_24h"] == 1
        # The 1h window is NOT yet active (hearing is 20h out)
        assert first["sent_1h"] == 0
        # A second tick is a no-op for the 24h window
        second = hearing_reminder_service.scan_and_notify(db)
        assert second["sent_24h"] == 0
    finally:
        db.close()


def test_1h_window_fires_independently(client) -> None:
    """When the hearing is <1h away both windows fire on the first
    tick - we shouldn't lose the 24h reminder just because we're
    already inside the 1h band."""
    c, SessionLocal = client
    h = _admin_h(c)
    _make_case_with_hearing(c, h, SessionLocal, hearing_in=timedelta(minutes=30))
    db = SessionLocal()
    try:
        stats = hearing_reminder_service.scan_and_notify(db)
        assert stats["sent_24h"] == 1
        assert stats["sent_1h"] == 1
    finally:
        db.close()


def test_past_hearings_are_ignored(client) -> None:
    c, SessionLocal = client
    h = _admin_h(c)
    _make_case_with_hearing(c, h, SessionLocal, hearing_in=timedelta(hours=-2))
    db = SessionLocal()
    try:
        stats = hearing_reminder_service.scan_and_notify(db)
        assert stats["sent_24h"] == 0
        assert stats["sent_1h"] == 0
    finally:
        db.close()


def test_closed_case_hearings_are_skipped(client) -> None:
    c, SessionLocal = client
    h = _admin_h(c)
    case_id, _ = _make_case_with_hearing(
        c, h, SessionLocal, hearing_in=timedelta(hours=20)
    )
    db = SessionLocal()
    try:
        case = db.get(Case, case_id)
        case.status = "Closed"
        db.commit()
    finally:
        db.close()
    db = SessionLocal()
    try:
        stats = hearing_reminder_service.scan_and_notify(db)
        assert stats["sent_24h"] == 0
        assert stats["sent_1h"] == 0
    finally:
        db.close()


def test_notification_lands_with_event_tag(client) -> None:
    c, SessionLocal = client
    h = _admin_h(c)
    _make_case_with_hearing(c, h, SessionLocal, hearing_in=timedelta(hours=20))
    db = SessionLocal()
    try:
        hearing_reminder_service.scan_and_notify(db)
    finally:
        db.close()

    db = SessionLocal()
    try:
        n = (
            db.query(Notification)
            .filter(Notification.event == "hearing.reminder")
            .order_by(Notification.id.desc())
            .first()
        )
        assert n is not None
        assert "Hearing" in n.title or "hearing" in n.body
    finally:
        db.close()
