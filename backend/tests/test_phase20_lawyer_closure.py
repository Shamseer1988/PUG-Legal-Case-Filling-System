"""Phase 20: explicit lawyer_approve transition + closable status set."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import *  # noqa: F401,F403
from app.models.case import (
    CASE_STATUS_FILED,
    CASE_STATUS_LAWYER_APPROVED,
    Case,
    CaseStatusUpdate,
    STAGE_LAWYER,
)
from app.models.user import Role, User, UserDivisionMap
from app.services import workflow_service
from app.services.seed import DEFAULT_ADMIN_EMAIL, DEFAULT_ADMIN_PASSWORD, run_seed


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "p20.db"
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


def _make_filed_case(c: TestClient, h: dict[str, str], SessionLocal) -> int:
    """Create a case and force-promote it to status=Filed/stage=Lawyer."""
    divs = c.get("/api/v1/masters/divisions", headers=h).json()
    div_id = divs[0]["id"]
    banks = c.get("/api/v1/masters/banks", headers=h).json()
    cust = c.post(
        "/api/v1/masters/customers",
        headers=h,
        json={"code": "CT20", "name": "Filed Co", "division_id": div_id},
    ).json()
    case = c.post(
        "/api/v1/cases",
        headers=h,
        json={
            "customer_id": cust["id"],
            "division_id": div_id,
            "is_civil": True,
            "cheques": [
                {
                    "cheque_number": "CH-20-1",
                    "bank_id": banks[0]["id"],
                    "amount": "1000.00",
                    "cheque_date": "2026-05-15",
                    "cheque_type": "Normal",
                    "bounce_reason": "Funds",
                },
            ],
        },
    ).json()
    case_id = case["id"]
    c.post(f"/api/v1/cases/{case_id}/submit", headers=h)
    # Force the case into status=Filed at stage=Lawyer to focus the
    # test on the new transition rather than walking all 6 approval
    # stages (already covered by test_workflow.py).
    db = SessionLocal()
    try:
        case_row = db.get(Case, case_id)
        case_row.status = CASE_STATUS_FILED
        case_row.current_stage = STAGE_LAWYER
        db.commit()
    finally:
        db.close()
    return case_id


def test_lawyer_approve_promotes_filed_to_lawyer_approved(client) -> None:
    c, SessionLocal = client
    h = _admin_h(c)
    case_id = _make_filed_case(c, h, SessionLocal)
    r = c.post(
        f"/api/v1/cases/{case_id}/transition",
        headers=h,
        json={"action": "lawyer_approve", "comment": "All paperwork in order"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == CASE_STATUS_LAWYER_APPROVED
    assert body["current_stage"] == STAGE_LAWYER

    # Audit row exists with the new action type
    db = SessionLocal()
    try:
        rows = (
            db.query(CaseStatusUpdate)
            .filter(CaseStatusUpdate.case_id == case_id)
            .order_by(CaseStatusUpdate.id)
            .all()
        )
        assert rows[-1].action_type == "lawyer_approve"
        assert rows[-1].to_status == CASE_STATUS_LAWYER_APPROVED
    finally:
        db.close()


def test_lawyer_approve_rejected_when_not_filed(client) -> None:
    c, SessionLocal = client
    h = _admin_h(c)
    # Fresh case still at Sales Manager / Submitted
    divs = c.get("/api/v1/masters/divisions", headers=h).json()
    div_id = divs[0]["id"]
    banks = c.get("/api/v1/masters/banks", headers=h).json()
    cust = c.post(
        "/api/v1/masters/customers",
        headers=h,
        json={"code": "CT20B", "name": "Pre-Filed Co", "division_id": div_id},
    ).json()
    case_id = c.post(
        "/api/v1/cases",
        headers=h,
        json={
            "customer_id": cust["id"],
            "division_id": div_id,
            "is_civil": True,
            "cheques": [
                {
                    "cheque_number": "CH-20-2",
                    "bank_id": banks[0]["id"],
                    "amount": "500.00",
                    "cheque_date": "2026-05-15",
                    "cheque_type": "Normal",
                    "bounce_reason": "Funds",
                },
            ],
        },
    ).json()["id"]
    c.post(f"/api/v1/cases/{case_id}/submit", headers=h)
    r = c.post(
        f"/api/v1/cases/{case_id}/transition",
        headers=h,
        json={"action": "lawyer_approve", "comment": "too early"},
    )
    assert r.status_code == 400
    detail = r.json()["detail"].lower()
    assert "fil" in detail or "stage" in detail


def test_close_from_lawyer_approved_works(client) -> None:
    c, SessionLocal = client
    h = _admin_h(c)
    case_id = _make_filed_case(c, h, SessionLocal)
    c.post(
        f"/api/v1/cases/{case_id}/transition",
        headers=h,
        json={"action": "lawyer_approve", "comment": "ok"},
    )
    # Now close — must accept Lawyer Approved as a closable status
    r = c.post(
        f"/api/v1/cases/{case_id}/close",
        headers=h,
        json={
            "closure_type": "settlement",
            "command": "Settled out of court",
            "settled_amount": "750.00",
            "settled_date": "2026-06-01",
            "settlement_agreement_ref": "AGR-20-1",
        },
    )
    assert r.status_code == 201, r.text
    # Case status should now be Closed
    case = c.get(f"/api/v1/cases/{case_id}", headers=h).json()
    assert case["status"] == "Closed"


def test_lawyer_approve_action_id_present_in_admin_capabilities(client) -> None:
    """Phase 14 matrix should already include case.lawyer.approve."""
    c, _ = client
    h = _admin_h(c)
    body = c.get("/api/v1/auth/me/capabilities", headers=h).json()
    assert "case.lawyer.approve" in body["actions"]


def test_cash_flow_report_exposes_closure_status(client) -> None:
    c, SessionLocal = client
    h = _admin_h(c)
    case_id = _make_filed_case(c, h, SessionLocal)
    case_no = c.get(f"/api/v1/cases/{case_id}", headers=h).json()["case_no"]

    # Run cash flow report BEFORE closing
    r = c.get(
        f"/api/v1/reports/case_cash_flow?case_no={case_no}",
        headers=h,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["case"]["is_closed"] is False
    assert body["case"]["closure_type"] == ""

    # Close it and re-run
    c.post(
        f"/api/v1/cases/{case_id}/close",
        headers=h,
        json={
            "closure_type": "court_cheque",
            "command": "Court cheque deposited",
            "settled_amount": "1000.00",
            "settled_date": "2026-06-10",
            "court_cheque_number": "CC-1",
        },
    )
    r = c.get(
        f"/api/v1/reports/case_cash_flow?case_no={case_no}",
        headers=h,
    )
    body = r.json()
    assert body["case"]["is_closed"] is True
    assert body["case"]["closure_type"] == "court_cheque"
    assert body["case"]["settled_amount"] == "1000.00"
    assert body["case"]["closed_by"]  # admin's name
