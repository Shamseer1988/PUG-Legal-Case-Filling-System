"""Phase 3 workflow tests: full happy path + clarify + reject."""

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


def _make_case(client: TestClient, h: dict[str, str]) -> int:
    divs = client.get("/api/v1/masters/divisions", headers=h).json()
    cust = client.post(
        "/api/v1/masters/customers",
        headers=h,
        json={"code": "WF1", "name": "Test Cust", "division_id": divs[0]["id"]},
    ).json()
    banks = client.get("/api/v1/masters/banks", headers=h).json()
    case = client.post(
        "/api/v1/cases",
        headers=h,
        json={
            "customer_id": cust["id"],
            "division_id": divs[0]["id"],
            "is_civil": True,
            "legal_filing_amount": "5000.00",
            "cheques": [
                {
                    "cheque_number": "CHQ-1",
                    "bank_id": banks[0]["id"],
                    "amount": "5000.00",
                    "cheque_type": "Normal",
                }
            ],
        },
    ).json()
    from tests.conftest import attach_default_signatory
    attach_default_signatory(client, h, case["id"])
    client.post(f"/api/v1/cases/{case['id']}/submit", headers=h)
    return int(case["id"])


def test_full_approval_chain(client: TestClient) -> None:
    h = _login(client)
    case_id = _make_case(client, h)

    expected = [
        ("Sales Manager", "Division Manager", "In Review"),
        ("Division Manager", "Audit", "In Review"),
        ("Audit", "Finance Manager", "In Review"),
        ("Finance Manager", "Executive Director", "In Review"),
        ("Executive Director", "Chairman / MD", "In Review"),
        ("Chairman / MD", "Lawyer", "Approved"),
    ]

    for at_stage, next_stage, expected_status in expected:
        case = client.get(f"/api/v1/cases/{case_id}", headers=h).json()
        assert case["current_stage"] == at_stage, f"want {at_stage}, got {case['current_stage']}"
        r = client.post(
            f"/api/v1/cases/{case_id}/transition",
            headers=h,
            json={"action": "approve", "comment": f"ok at {at_stage}"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["current_stage"] == next_stage
        assert body["status"] == expected_status

    timeline = client.get(f"/api/v1/cases/{case_id}/timeline", headers=h).json()
    assert any(t["action_type"] == "submit" for t in timeline)
    assert sum(1 for t in timeline if t["action_type"] == "approve") == len(expected)


def test_clarification_then_resubmit(client: TestClient) -> None:
    h = _login(client)
    case_id = _make_case(client, h)

    # SM requests clarification
    r = client.post(
        f"/api/v1/cases/{case_id}/transition",
        headers=h,
        json={"action": "request_clarification", "comment": "Need supporting doc"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "Clarification Requested"
    assert r.json()["current_stage"] == "Accountant"

    # Accountant resubmits
    r = client.post(
        f"/api/v1/cases/{case_id}/transition",
        headers=h,
        json={"action": "resubmit", "comment": "Doc attached"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["current_stage"] == "Sales Manager"
    assert r.json()["status"] == "In Review"


def test_reject_requires_comment(client: TestClient) -> None:
    h = _login(client)
    case_id = _make_case(client, h)
    r = client.post(
        f"/api/v1/cases/{case_id}/transition",
        headers=h,
        json={"action": "reject", "comment": ""},
    )
    assert r.status_code == 400


def test_inbox_lists_submitted_case(client: TestClient) -> None:
    h = _login(client)
    case_id = _make_case(client, h)
    inbox = client.get("/api/v1/approvals/inbox", headers=h).json()
    assert any(item["id"] == case_id for item in inbox)
