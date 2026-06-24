"""Phase 23: approvals inbox ``scope=mine`` query filter."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import *  # noqa: F401,F403
from app.models.case import Case
from app.models.user import Role, User, UserDivisionMap
from app.services.seed import DEFAULT_ADMIN_EMAIL, DEFAULT_ADMIN_PASSWORD, run_seed


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "p23.db"
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


def _login(c: TestClient, email: str) -> dict[str, str]:
    r = c.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Pass@1234"},
    )
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _setup_two_sales_managers_one_submitted_case(c: TestClient, SessionLocal) -> tuple[str, str, int, int]:
    """Returns (sm1_email, sm2_email, sm1_id, case_id) with the case
    assigned to SM1 and waiting at the Sales Manager stage."""
    h = _admin_h(c)
    divs = c.get("/api/v1/masters/divisions", headers=h).json()
    div_id = divs[0]["id"]
    banks = c.get("/api/v1/masters/banks", headers=h).json()
    cust = c.post(
        "/api/v1/masters/customers",
        headers=h,
        json={"code": "CT23", "name": "Acme23", "division_id": div_id},
    ).json()

    db = SessionLocal()
    try:
        sm_role = db.query(Role).filter(Role.name == "Sales Manager").first()
        sm1 = User(
            email="sm1@pug.local",
            password_hash=hash_password("Pass@1234"),
            full_name="Sales Mgr 1",
            role_id=sm_role.id,
        )
        sm2 = User(
            email="sm2@pug.local",
            password_hash=hash_password("Pass@1234"),
            full_name="Sales Mgr 2",
            role_id=sm_role.id,
        )
        db.add_all([sm1, sm2])
        db.flush()
        # Both SMs cover the same division so the inbox sees both
        db.add(UserDivisionMap(user_id=sm1.id, division_id=div_id))
        db.add(UserDivisionMap(user_id=sm2.id, division_id=div_id))
        db.commit()
        sm1_id = sm1.id
    finally:
        db.close()

    case_id = c.post(
        "/api/v1/cases",
        headers=h,
        json={
            "customer_id": cust["id"],
            "division_id": div_id,
            "is_civil": True,
            "sales_manager_id": sm1_id,
            "cheques": [
                {
                    "cheque_number": "CH-23-1",
                    "bank_id": banks[0]["id"],
                    "amount": "1000.00",
                    "cheque_date": "2026-05-15",
                    "cheque_type": "Normal",
                    "bounce_reason": "Funds",
                },
            ],
        },
    ).json()["id"]
    c.post(f"/api/v1/cases/{case_id}/submit", headers=h)
    return "sm1@pug.local", "sm2@pug.local", sm1_id, case_id


def test_scope_mine_hides_cases_assigned_to_teammates(client) -> None:
    c, SessionLocal = client
    sm1_email, sm2_email, _, case_id = _setup_two_sales_managers_one_submitted_case(c, SessionLocal)

    # SM1 sees the case in both scopes (assigned)
    sm1 = _login(c, sm1_email)
    all_rows = c.get("/api/v1/approvals/inbox", headers=sm1).json()
    mine_rows = c.get("/api/v1/approvals/inbox?scope=mine", headers=sm1).json()
    assert any(r["id"] == case_id for r in all_rows)
    assert any(r["id"] == case_id and r["assigned_to_me"] for r in mine_rows)

    # SM2 sees the case in scope=all (same permission + division) but
    # NOT in scope=mine, because they aren't the designated signatory.
    sm2 = _login(c, sm2_email)
    all_rows = c.get("/api/v1/approvals/inbox", headers=sm2).json()
    mine_rows = c.get("/api/v1/approvals/inbox?scope=mine", headers=sm2).json()
    assert any(r["id"] == case_id for r in all_rows)
    assert all(r["id"] != case_id for r in mine_rows)


def test_scope_defaults_to_all(client) -> None:
    c, SessionLocal = client
    _, _sm2_email, _, case_id = _setup_two_sales_managers_one_submitted_case(c, SessionLocal)
    sm2 = _login(c, "sm2@pug.local")
    # No scope param -> behaves like scope=all
    rows = c.get("/api/v1/approvals/inbox", headers=sm2).json()
    assert any(r["id"] == case_id for r in rows)


def test_clarification_owner_counted_as_mine(client) -> None:
    """When an SM bounces a case back for clarification, the case
    returns to the Accountant who authored it; that accountant should
    see it under scope=mine so they know to resubmit."""
    c, SessionLocal = client
    sm1_email, _, _, case_id = _setup_two_sales_managers_one_submitted_case(c, SessionLocal)

    # SM1 requests clarification -> case goes back to Accountant
    sm1 = _login(c, sm1_email)
    r = c.post(
        f"/api/v1/cases/{case_id}/transition",
        headers=sm1,
        json={"action": "request_clarification", "comment": "Need invoice"},
    )
    assert r.status_code == 200

    admin = _admin_h(c)
    rows = c.get("/api/v1/approvals/inbox?scope=mine", headers=admin).json()
    # Admin authored the case (seeded admin = case creator), so the
    # Clarification Requested case must show under their "mine" tab.
    assert any(
        r["id"] == case_id and r["status"] == "Clarification Requested"
        for r in rows
    )
