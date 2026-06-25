"""Phase 46: clarification can be directed at any stage below the requester."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import *  # noqa: F401,F403
from app.models.case import STAGE_ACCOUNTANT, STAGE_SALES_MGR, STAGE_DIV_MGR
from app.models.user import Role, User
from app.services.seed import DEFAULT_ADMIN_EMAIL, DEFAULT_ADMIN_PASSWORD, run_seed


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "phase46.db"
    storage_dir = tmp_path / "storage"
    storage_dir.mkdir()
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("STORAGE_LOCAL_PATH", str(storage_dir))
    monkeypatch.delenv("SMTP_HOST", raising=False)

    from app.core import config as cfg_mod
    monkeypatch.setattr(cfg_mod.settings, "storage_local_path", str(storage_dir))

    engine = create_engine(f"sqlite:///{db_path}", future=True)
    SL = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(engine)

    def override_get_db():
        db = SL()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    from app.db import session as session_mod
    import app.services.seed as seed_mod

    orig = session_mod.SessionLocal
    orig_seed = seed_mod.SessionLocal
    session_mod.SessionLocal = SL
    seed_mod.SessionLocal = SL
    try:
        run_seed()
        yield TestClient(app), SL
    finally:
        session_mod.SessionLocal = orig
        seed_mod.SessionLocal = orig_seed
        app.dependency_overrides.clear()


_SEQ = [0]


def _seq():
    _SEQ[0] += 1
    return _SEQ[0]


def _login(c: TestClient, email: str, pw: str = "Pass@1234") -> dict:
    r = c.post("/api/v1/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _make_user(SL, role_name: str, n: int, is_super: bool = False) -> User:
    db = SL()
    try:
        role = db.query(Role).filter(Role.name == role_name).first()
        u = User(
            email=f"{role_name.lower().replace(' ', '_')}_{n}@pug.local",
            password_hash=hash_password("Pass@1234"),
            full_name=f"{role_name} {n}",
            role_id=role.id,
            is_active=True,
            is_super=is_super,
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        return u
    finally:
        db.close()


def _setup(c: TestClient, SL):
    """Create a submitted case with SM, DM, and Accountant users."""
    from tests.conftest import attach_default_signatory

    n = _seq()
    admin_h = _login(c, DEFAULT_ADMIN_EMAIL, DEFAULT_ADMIN_PASSWORD)

    div = c.post(
        "/api/v1/masters/divisions",
        headers=admin_h,
        json={"code": f"D46{n}", "name": f"Div46-{n}", "is_active": True},
    )
    assert div.status_code == 201, div.text
    div_id = div.json()["id"]

    cust = c.post(
        "/api/v1/masters/customers",
        headers=admin_h,
        json={"code": f"C46{n}", "name": f"Cust46-{n}", "division_id": div_id, "is_active": True},
    )
    assert cust.status_code == 201, cust.text
    cust_id = cust.json()["id"]

    bank = c.post(
        "/api/v1/masters/banks",
        headers=admin_h,
        json={"code": f"BK{n}", "name": f"Bank{n}", "is_active": True},
    )
    assert bank.status_code == 201, bank.text
    bank_id = bank.json()["id"]

    # SM and DM are super so they bypass division scoping for approval actions
    sm = _make_user(SL, "Sales Manager", n, is_super=True)
    dm = _make_user(SL, "Division Manager", n, is_super=True)
    # Accountant is NOT super — permission checks must apply correctly for negative tests
    accountant = _make_user(SL, "Accountant", n, is_super=False)

    acct_h = _login(c, accountant.email)

    # Accountant creates the case (so created_by_id == accountant.id).
    # Cheques are embedded in the creation payload, not via a separate endpoint.
    case_r = c.post(
        "/api/v1/cases",
        headers=acct_h,
        json={
            "customer_id": cust_id,
            "division_id": div_id,
            "customer_type": "Retail",
            "actual_due_amount": "1000",
            "legal_filing_amount": "1000",
            "sales_manager_id": sm.id,
            "division_manager_id": dm.id,
            "cheques": [
                {
                    "cheque_number": f"CHQ{n}",
                    "bank_id": bank_id,
                    "amount": "1000",
                    "cheque_date": "2025-01-01",
                    "cheque_type": "Normal",
                    "bounce_reason": "NSF",
                }
            ],
        },
    )
    assert case_r.status_code == 201, case_r.text
    case_id = case_r.json()["id"]
    case_dict = case_r.json()

    # Phase 40: attach a cheque signatory (admin handles this as super user)
    attach_default_signatory(c, admin_h, case_dict)

    # Submit the case
    sub = c.post(f"/api/v1/cases/{case_id}/submit", headers=acct_h)
    assert sub.status_code == 200, sub.text
    assert sub.json()["current_stage"] == "Sales Manager"

    return case_id, sm, dm, accountant, admin_h, acct_h


# ---- Sales Manager can only ask Accountant ----

def test_sm_clarification_defaults_to_accountant(client):
    c, SL = client
    case_id, sm, dm, accountant, admin_h, acct_h = _setup(c, SL)
    sm_h = _login(c, sm.email)

    r = c.post(
        f"/api/v1/cases/{case_id}/transition",
        headers=sm_h,
        json={"action": "request_clarification", "comment": "Need bank details"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "Clarification Requested"
    assert data["current_stage"] == STAGE_ACCOUNTANT
    assert data["clarify_from_stage"] == STAGE_ACCOUNTANT


def test_sm_clarification_explicit_accountant(client):
    c, SL = client
    case_id, sm, dm, accountant, admin_h, acct_h = _setup(c, SL)
    sm_h = _login(c, sm.email)

    r = c.post(
        f"/api/v1/cases/{case_id}/transition",
        headers=sm_h,
        json={"action": "request_clarification", "comment": "Please clarify", "clarify_from_stage": "Accountant"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["clarify_from_stage"] == STAGE_ACCOUNTANT


def test_sm_cannot_ask_higher_stage(client):
    """SM cannot direct clarification at Division Manager (who is above SM)."""
    c, SL = client
    case_id, sm, dm, accountant, admin_h, acct_h = _setup(c, SL)
    sm_h = _login(c, sm.email)

    r = c.post(
        f"/api/v1/cases/{case_id}/transition",
        headers=sm_h,
        json={"action": "request_clarification", "comment": "x", "clarify_from_stage": "Division Manager"},
    )
    assert r.status_code == 400, r.text


def test_accountant_can_resubmit_sm_clarification(client):
    c, SL = client
    case_id, sm, dm, accountant, admin_h, acct_h = _setup(c, SL)
    sm_h = _login(c, sm.email)

    c.post(
        f"/api/v1/cases/{case_id}/transition",
        headers=sm_h,
        json={"action": "request_clarification", "comment": "Need docs"},
    )

    # Accountant resubmits
    r = c.post(
        f"/api/v1/cases/{case_id}/transition",
        headers=acct_h,
        json={"action": "resubmit", "comment": "Docs attached"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    # Case goes back to SM (who asked)
    assert data["current_stage"] == STAGE_SALES_MGR
    assert data["status"] == "In Review"
    assert data["clarify_from_stage"] is None


# ---- DM can ask SM or Accountant ----

def _advance_to_dm(c, case_id, sm_h, admin_h):
    """SM approves to push case to Division Manager."""
    r = c.post(
        f"/api/v1/cases/{case_id}/transition",
        headers=sm_h,
        json={"action": "approve", "comment": "OK"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["current_stage"] == "Division Manager"


def test_dm_can_ask_sales_manager(client):
    c, SL = client
    case_id, sm, dm, accountant, admin_h, acct_h = _setup(c, SL)
    sm_h = _login(c, sm.email)
    dm_h = _login(c, dm.email)

    _advance_to_dm(c, case_id, sm_h, admin_h)

    r = c.post(
        f"/api/v1/cases/{case_id}/transition",
        headers=dm_h,
        json={
            "action": "request_clarification",
            "comment": "SM please check bounced cheque",
            "clarify_from_stage": "Sales Manager",
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "Clarification Requested"
    assert data["current_stage"] == STAGE_SALES_MGR
    assert data["clarify_from_stage"] == STAGE_SALES_MGR


def test_dm_can_ask_accountant(client):
    c, SL = client
    case_id, sm, dm, accountant, admin_h, acct_h = _setup(c, SL)
    sm_h = _login(c, sm.email)
    dm_h = _login(c, dm.email)

    _advance_to_dm(c, case_id, sm_h, admin_h)

    r = c.post(
        f"/api/v1/cases/{case_id}/transition",
        headers=dm_h,
        json={
            "action": "request_clarification",
            "comment": "Need original docs from accountant",
            "clarify_from_stage": "Accountant",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["current_stage"] == STAGE_ACCOUNTANT
    assert r.json()["clarify_from_stage"] == STAGE_ACCOUNTANT


def test_sm_can_resubmit_dm_clarification(client):
    """When DM asks SM, SM can answer and case returns to DM."""
    c, SL = client
    case_id, sm, dm, accountant, admin_h, acct_h = _setup(c, SL)
    sm_h = _login(c, sm.email)
    dm_h = _login(c, dm.email)

    _advance_to_dm(c, case_id, sm_h, admin_h)
    c.post(
        f"/api/v1/cases/{case_id}/transition",
        headers=dm_h,
        json={
            "action": "request_clarification",
            "comment": "SM please check",
            "clarify_from_stage": "Sales Manager",
        },
    )

    # SM resubmits
    r = c.post(
        f"/api/v1/cases/{case_id}/transition",
        headers=sm_h,
        json={"action": "resubmit", "comment": "Checked and confirmed"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["current_stage"] == STAGE_DIV_MGR
    assert data["status"] == "In Review"
    assert data["clarify_from_stage"] is None


def test_accountant_cannot_resubmit_sm_directed_clarification(client):
    """When DM asks SM, accountant should NOT be able to resubmit."""
    c, SL = client
    case_id, sm, dm, accountant, admin_h, acct_h = _setup(c, SL)
    sm_h = _login(c, sm.email)
    dm_h = _login(c, dm.email)

    _advance_to_dm(c, case_id, sm_h, admin_h)
    c.post(
        f"/api/v1/cases/{case_id}/transition",
        headers=dm_h,
        json={
            "action": "request_clarification",
            "comment": "SM question",
            "clarify_from_stage": "Sales Manager",
        },
    )

    r = c.post(
        f"/api/v1/cases/{case_id}/transition",
        headers=acct_h,
        json={"action": "resubmit", "comment": "Accountant tries"},
    )
    assert r.status_code == 403, r.text


def test_inbox_routes_clarification_to_sm(client):
    """When DM asks SM, the case appears in SM's inbox not accountant's."""
    c, SL = client
    case_id, sm, dm, accountant, admin_h, acct_h = _setup(c, SL)
    sm_h = _login(c, sm.email)
    dm_h = _login(c, dm.email)

    _advance_to_dm(c, case_id, sm_h, admin_h)
    c.post(
        f"/api/v1/cases/{case_id}/transition",
        headers=dm_h,
        json={
            "action": "request_clarification",
            "comment": "SM please check",
            "clarify_from_stage": "Sales Manager",
        },
    )

    sm_inbox = c.get("/api/v1/approvals/inbox", headers=sm_h)
    assert sm_inbox.status_code == 200
    sm_ids = [i["id"] for i in sm_inbox.json()]
    assert case_id in sm_ids, "Case should appear in SM's inbox"

    acct_inbox = c.get("/api/v1/approvals/inbox", headers=acct_h)
    assert acct_inbox.status_code == 200
    acct_ids = [i["id"] for i in acct_inbox.json()]
    assert case_id not in acct_ids, "Case should NOT appear in accountant's inbox"


def test_case_read_exposes_clarify_from_stage(client):
    c, SL = client
    case_id, sm, dm, accountant, admin_h, acct_h = _setup(c, SL)
    sm_h = _login(c, sm.email)
    dm_h = _login(c, dm.email)

    _advance_to_dm(c, case_id, sm_h, admin_h)
    c.post(
        f"/api/v1/cases/{case_id}/transition",
        headers=dm_h,
        json={
            "action": "request_clarification",
            "comment": "Need info",
            "clarify_from_stage": "Sales Manager",
        },
    )

    r = c.get(f"/api/v1/cases/{case_id}", headers=admin_h)
    assert r.status_code == 200
    assert r.json()["clarify_from_stage"] == "Sales Manager"
