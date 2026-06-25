"""Phase 2: case create / cheque / submit / print smoke tests."""

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


def _make_customer(client: TestClient, h: dict[str, str]) -> dict:
    # Need a division first
    divs = client.get("/api/v1/masters/divisions", headers=h).json()
    div_id = divs[0]["id"]
    r = client.post(
        "/api/v1/masters/customers",
        headers=h,
        json={"code": "C001", "name": "Acme Trading", "division_id": div_id},
    )
    assert r.status_code == 201, r.text
    return {**r.json(), "division_id": div_id}


def test_case_create_submit_print(client: TestClient) -> None:
    h = _login(client)
    cust = _make_customer(client, h)
    banks = client.get("/api/v1/masters/banks", headers=h).json()

    payload = {
        "customer_id": cust["id"],
        "division_id": cust["division_id"],
        "customer_type": "Retail",
        "actual_due_amount": "12500.00",
        "legal_filing_amount": "12000.00",
        "deposit_date": "2026-06-01",
        "is_criminal": True,
        "is_civil": False,
        "commands": "Initial filing - customer non-responsive.",
        "cheques": [
            {
                "cheque_number": "00012345",
                "bank_id": banks[0]["id"],
                "amount": "6000.00",
                "cheque_date": "2026-05-15",
                "cheque_type": "Normal",
                "bounce_reason": "Insufficient funds",
            },
            {
                "cheque_number": "00012346",
                "bank_id": banks[0]["id"],
                "amount": "6000.00",
                "cheque_date": "2026-05-30",
                "cheque_type": "Guarantee",
                "bounce_reason": "",
            },
        ],
    }
    r = client.post("/api/v1/cases", headers=h, json=payload)
    assert r.status_code == 201, r.text
    case = r.json()
    assert case["case_no"].startswith("PUG-LEGAL-")
    assert len(case["cheques"]) == 2
    assert case["status"] == "Draft"
    case_id = case["id"]

    # List should include it
    rows = client.get("/api/v1/cases", headers=h).json()
    assert any(row["id"] == case_id for row in rows)

    from tests.conftest import attach_default_signatory
    attach_default_signatory(client, h, case_id)

    # Submit
    r = client.post(f"/api/v1/cases/{case_id}/submit", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "Submitted"

    # Editing after submit should fail
    from app.db import session as session_mod
    from app.models.user import User as UserModel
    db_session = session_mod.SessionLocal()
    try:
        admin_db_user = db_session.query(UserModel).filter(UserModel.email == DEFAULT_ADMIN_EMAIL).first()
        if admin_db_user:
            admin_db_user.is_super = False
            db_session.commit()
    finally:
        db_session.close()

    # Transition the case to Division Manager stage (close the edit window)
    client.post(
        f"/api/v1/cases/{case_id}/transition",
        headers=h,
        json={"action": "approve", "comment": "moving past sales manager"},
    )

    r = client.patch(f"/api/v1/cases/{case_id}", headers=h, json={"commands": "no"})
    assert r.status_code == 400

    # Print returns PDF
    r = client.get(f"/api/v1/cases/{case_id}/print", headers=h)
    assert r.status_code == 200
    assert r.content.startswith(b"%PDF")


def test_submit_without_cheques_rejected(client: TestClient) -> None:
    h = _login(client)
    cust = _make_customer(client, h)
    r = client.post(
        "/api/v1/cases",
        headers=h,
        json={
            "customer_id": cust["id"],
            "division_id": cust["division_id"],
            "is_civil": True,
        },
    )
    case_id = r.json()["id"]
    r = client.post(f"/api/v1/cases/{case_id}/submit", headers=h)
    assert r.status_code == 400
