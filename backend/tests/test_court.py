"""Phase 4 tests: court filing, hearings, cash request lifecycle."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import *  # noqa: F401,F403
from app.services.seed import DEFAULT_ADMIN_EMAIL, DEFAULT_ADMIN_PASSWORD, run_seed


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
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

    orig = session_mod.SessionLocal
    session_mod.SessionLocal = TestingSessionLocal
    try:
        run_seed()
        yield TestClient(app)
    finally:
        session_mod.SessionLocal = orig
        app.dependency_overrides.clear()


def _login(client: TestClient) -> dict[str, str]:
    r = client.post(
        "/api/v1/auth/login",
        json={"email": DEFAULT_ADMIN_EMAIL, "password": DEFAULT_ADMIN_PASSWORD},
    )
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _approved_case(client: TestClient, h: dict[str, str]) -> int:
    """Create a case and walk it through the full approval chain (admin can act all)."""
    divs = client.get("/api/v1/masters/divisions", headers=h).json()
    cust = client.post(
        "/api/v1/masters/customers",
        headers=h,
        json={"code": "CT1", "name": "Court Test", "division_id": divs[0]["id"]},
    ).json()
    banks = client.get("/api/v1/masters/banks", headers=h).json()
    case = client.post(
        "/api/v1/cases",
        headers=h,
        json={
            "customer_id": cust["id"],
            "division_id": divs[0]["id"],
            "is_civil": True,
            "legal_filing_amount": "9000.00",
            "cheques": [
                {
                    "cheque_number": "CHQ-CT",
                    "bank_id": banks[0]["id"],
                    "amount": "9000.00",
                    "cheque_type": "Normal",
                }
            ],
        },
    ).json()
    case_id = int(case["id"])
    from tests.conftest import attach_default_signatory
    attach_default_signatory(client, h, case_id)
    client.post(f"/api/v1/cases/{case_id}/submit", headers=h)
    for _ in range(6):
        client.post(
            f"/api/v1/cases/{case_id}/transition",
            headers=h,
            json={"action": "approve", "comment": "ok"},
        )
    assert (
        client.get(f"/api/v1/cases/{case_id}", headers=h).json()["status"] == "Approved"
    )
    return case_id


def test_court_filing_promotes_status_to_filed(client: TestClient) -> None:
    h = _login(client)
    case_id = _approved_case(client, h)
    r = client.post(
        f"/api/v1/cases/{case_id}/court-filing",
        headers=h,
        json={
            "police_case_no": "POL/2026/12345",
            "court_case_no": "COURT/2026/9876",
            "filed_court": "Court of First Instance",
            "filed_date": "2026-06-10",
            "notes": "Filed and acknowledged.",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["police_case_no"] == "POL/2026/12345"

    case = client.get(f"/api/v1/cases/{case_id}", headers=h).json()
    assert case["status"] == "Filed"
    assert case["current_stage"] == "Lawyer"


def test_hearings_and_calendar(client: TestClient) -> None:
    h = _login(client)
    case_id = _approved_case(client, h)
    client.post(
        f"/api/v1/cases/{case_id}/court-filing",
        headers=h,
        json={"police_case_no": "POL", "court_case_no": "C1"},
    )
    next_dt = (datetime.now(timezone.utc) + timedelta(days=14)).isoformat()
    r = client.post(
        f"/api/v1/cases/{case_id}/hearings",
        headers=h,
        json={
            "hearing_date": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
            "location": "Court Room 3",
            "hearing_type": "First Hearing",
            "outcome": "Counsel presented.",
            "next_hearing_date": next_dt,
        },
    )
    assert r.status_code == 201, r.text

    cal = client.get("/api/v1/hearings/calendar?days=60", headers=h).json()
    assert any(c["case_id"] == case_id for c in cal)
    # next hearing entry also appears
    assert sum(1 for c in cal if c["case_id"] == case_id) >= 2


def test_cash_request_lifecycle(client: TestClient) -> None:
    h = _login(client)
    case_id = _approved_case(client, h)
    # Cash request
    r = client.post(
        f"/api/v1/cases/{case_id}/cash-requests",
        headers=h,
        json={"amount": "750.00", "purpose": "Court fees"},
    )
    assert r.status_code == 201, r.text
    cr_id = r.json()["id"]
    assert r.json()["status"] == "Requested"

    # Approve
    r = client.post(
        f"/api/v1/cash-requests/{cr_id}/approve",
        headers=h,
        json={"comment": "Within limits"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "Approved"

    # Pay
    r = client.post(
        f"/api/v1/cash-requests/{cr_id}/pay",
        headers=h,
        json={"payment_reference": "VCH-001"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "Paid"

    summary = client.get(f"/api/v1/cases/{case_id}/spend-summary", headers=h).json()
    assert summary["total_paid"] == "750.00"
    assert summary["open_count"] == 0


def test_court_filing_blocked_before_approval(client: TestClient) -> None:
    h = _login(client)
    divs = client.get("/api/v1/masters/divisions", headers=h).json()
    cust = client.post(
        "/api/v1/masters/customers",
        headers=h,
        json={"code": "CTX", "name": "Blocked", "division_id": divs[0]["id"]},
    ).json()
    banks = client.get("/api/v1/masters/banks", headers=h).json()
    case = client.post(
        "/api/v1/cases",
        headers=h,
        json={
            "customer_id": cust["id"],
            "division_id": divs[0]["id"],
            "is_civil": True,
            "cheques": [
                {"cheque_number": "C", "bank_id": banks[0]["id"], "amount": "1", "cheque_type": "Normal"}
            ],
        },
    ).json()
    r = client.post(
        f"/api/v1/cases/{case['id']}/court-filing", headers=h, json={"police_case_no": "X"}
    )
    assert r.status_code == 400
