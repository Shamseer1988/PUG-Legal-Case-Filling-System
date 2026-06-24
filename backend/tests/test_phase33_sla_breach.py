"""Phase 33: scheduled SLA breach escalation."""

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
from app.models.notification import Notification
from app.services import sla_service
from .conftest import attach_default_signatory
from app.services.seed import DEFAULT_ADMIN_EMAIL, DEFAULT_ADMIN_PASSWORD, run_seed


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "p33.db"
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


def _make_submitted_case(c: TestClient, h: dict[str, str]) -> int:
    divs = c.get("/api/v1/masters/divisions", headers=h).json()
    div_id = divs[0]["id"]
    banks = c.get("/api/v1/masters/banks", headers=h).json()
    cust = c.post(
        "/api/v1/masters/customers",
        headers=h,
        json={"code": "SLA1", "name": "SLA Co", "division_id": div_id},
    ).json()
    me = c.get("/api/v1/auth/me", headers=h).json()
    case = c.post(
        "/api/v1/cases",
        headers=h,
        json={
            "customer_id": cust["id"],
            "division_id": div_id,
            "is_civil": True,
            # The admin user is in every signatory slot in dev seed,
            # which is fine for an SLA test — we just need ANY user
            # assigned to the current stage.
            "sales_manager_id": me["id"],
            "division_manager_id": me["id"],
            "auditor_id": me["id"],
            "fm_id": me["id"],
            "ed_id": me["id"],
            "chairman_id": me["id"],
            "cheques": [
                {
                    "cheque_number": "CH-SLA-1",
                    "bank_id": banks[0]["id"],
                    "amount": "100.00",
                    "cheque_date": "2026-05-15",
                    "cheque_type": "Normal",
                    "bounce_reason": "Funds",
                },
            ],
        },
    ).json()
    case_id = case["id"]
    attach_default_signatory(c, h, case)
    c.post(f"/api/v1/cases/{case_id}/submit", headers=h)
    return case_id


def _force_overdue(SessionLocal, case_id: int, *, hours_overdue: int = 1) -> None:
    db = SessionLocal()
    try:
        case = db.get(Case, case_id)
        # Set due in the past, clear any prior flag.
        case.sla_due_at = datetime.now(timezone.utc) - timedelta(
            hours=hours_overdue
        )
        case.sla_breach_notified_at = None
        db.commit()
    finally:
        db.close()


def test_scan_skips_cases_within_sla(client) -> None:
    c, SessionLocal = client
    h = _admin_h(c)
    _make_submitted_case(c, h)
    db = SessionLocal()
    try:
        stats = sla_service.scan_and_escalate(db)
        assert stats == {"scanned": 0, "escalated": 0}
    finally:
        db.close()


def test_scan_escalates_breached_case_once(client) -> None:
    c, SessionLocal = client
    h = _admin_h(c)
    case_id = _make_submitted_case(c, h)
    _force_overdue(SessionLocal, case_id)

    db = SessionLocal()
    try:
        first = sla_service.scan_and_escalate(db)
        assert first["escalated"] == 1
        # A second tick is a no-op until the case moves stage
        second = sla_service.scan_and_escalate(db)
        assert second == {"scanned": 0, "escalated": 0}
    finally:
        db.close()

    # And the assignee got a real in-app notification with the right event
    db = SessionLocal()
    try:
        notif = (
            db.query(Notification)
            .filter(Notification.event == "case.sla_breached")
            .order_by(Notification.id.desc())
            .first()
        )
        assert notif is not None
        assert str(case_id) in notif.link
        assert "SLA" in notif.title
    finally:
        db.close()


def test_breach_flag_clears_on_next_stage(client) -> None:
    """Once the case advances, the next stage's SLA gets a fresh ping
    if it also overruns — sla_breach_notified_at is cleared in
    workflow._set_stage."""
    c, SessionLocal = client
    h = _admin_h(c)
    case_id = _make_submitted_case(c, h)
    _force_overdue(SessionLocal, case_id)
    db = SessionLocal()
    try:
        sla_service.scan_and_escalate(db)
    finally:
        db.close()

    # Advance the case (admin has all approve perms in dev seed)
    r = c.post(
        f"/api/v1/cases/{case_id}/transition",
        headers=h,
        json={"action": "approve", "comment": "moving"},
    )
    assert r.status_code == 200, r.text

    db = SessionLocal()
    try:
        case = db.get(Case, case_id)
        assert case.sla_breach_notified_at is None
        # And current_stage has advanced past Sales Manager
        assert case.current_stage != "Sales Manager"
    finally:
        db.close()

    # Force the new stage overdue, scanner should fire again
    _force_overdue(SessionLocal, case_id)
    db = SessionLocal()
    try:
        stats = sla_service.scan_and_escalate(db)
        assert stats["escalated"] == 1
    finally:
        db.close()


def test_scan_ignores_closed_and_rejected(client) -> None:
    """A breached row with status=Rejected must not be escalated -
    nobody is waiting on it anymore."""
    c, SessionLocal = client
    h = _admin_h(c)
    case_id = _make_submitted_case(c, h)
    _force_overdue(SessionLocal, case_id)
    db = SessionLocal()
    try:
        case = db.get(Case, case_id)
        case.status = "Rejected"
        db.commit()
    finally:
        db.close()
    db = SessionLocal()
    try:
        stats = sla_service.scan_and_escalate(db)
        assert stats == {"scanned": 0, "escalated": 0}
    finally:
        db.close()


def test_find_breaches_returns_ordered_list(client) -> None:
    c, SessionLocal = client
    h = _admin_h(c)
    case_id = _make_submitted_case(c, h)
    _force_overdue(SessionLocal, case_id, hours_overdue=3)
    db = SessionLocal()
    try:
        rows = sla_service.find_breaches(db)
        ids = [r.id for r in rows]
        assert case_id in ids
    finally:
        db.close()
