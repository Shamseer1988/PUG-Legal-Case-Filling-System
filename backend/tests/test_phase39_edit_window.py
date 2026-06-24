"""Phase 39: scoped masters + Accountant edit window + closure discount."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import *  # noqa: F401,F403
from app.models.user import User, UserDivisionMap
from app.services.seed import DEFAULT_ADMIN_EMAIL, DEFAULT_ADMIN_PASSWORD, run_seed


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "p39.db"
    storage_dir = tmp_path / "storage"
    storage_dir.mkdir()
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("STORAGE_LOCAL_PATH", str(storage_dir))
    monkeypatch.delenv("SMTP_HOST", raising=False)

    from app.core import config as config_mod
    monkeypatch.setattr(config_mod.settings, "storage_local_path", str(storage_dir))

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


def _make_accountant(c, h, SessionLocal, *, email: str, division_id: int):
    """Create an Accountant user mapped to exactly one division."""
    roles = c.get("/api/v1/roles", headers=h).json()
    role_id = next(r["id"] for r in roles if r["name"] == "Accountant")
    body = {
        "email": email,
        "full_name": email.split("@")[0],
        "password": "Pa55word!",
        "role_id": role_id,
        "is_active": True,
        "is_super": False,
        "is_all_divisions": False,
        "division_ids": [division_id],
    }
    r = c.post("/api/v1/users", headers=h, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _login(c, email, password="Pa55word!"):
    r = c.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# ============================== Scoped masters ==============================
def test_masters_divisions_scoped_for_non_super(client) -> None:
    c, SessionLocal = client
    admin_h = _admin_h(c)

    # Make two divisions.
    divs_before = c.get("/api/v1/masters/divisions", headers=admin_h).json()
    div_a = c.post(
        "/api/v1/masters/divisions",
        headers=admin_h,
        json={"code": "P39A", "name": "P39 Alpha"},
    ).json()
    div_b = c.post(
        "/api/v1/masters/divisions",
        headers=admin_h,
        json={"code": "P39B", "name": "P39 Beta"},
    ).json()

    _make_accountant(c, admin_h, SessionLocal, email="p39alpha@x.com", division_id=div_a["id"])

    acc_h = _login(c, "p39alpha@x.com")
    visible = c.get("/api/v1/masters/divisions", headers=acc_h).json()
    ids = {d["id"] for d in visible}
    assert div_a["id"] in ids
    assert div_b["id"] not in ids, "Accountant must not see other divisions"

    # Admin still sees both
    admin_visible = c.get("/api/v1/masters/divisions", headers=admin_h).json()
    admin_ids = {d["id"] for d in admin_visible}
    assert div_a["id"] in admin_ids and div_b["id"] in admin_ids


def test_masters_customers_scoped_to_user_division(client) -> None:
    c, SessionLocal = client
    admin_h = _admin_h(c)

    div_a = c.post(
        "/api/v1/masters/divisions",
        headers=admin_h,
        json={"code": "P39CA", "name": "Alpha"},
    ).json()
    div_b = c.post(
        "/api/v1/masters/divisions",
        headers=admin_h,
        json={"code": "P39CB", "name": "Beta"},
    ).json()
    cust_a = c.post(
        "/api/v1/masters/customers",
        headers=admin_h,
        json={"code": "CA39", "name": "Alpha Customer", "division_id": div_a["id"]},
    ).json()
    cust_b = c.post(
        "/api/v1/masters/customers",
        headers=admin_h,
        json={"code": "CB39", "name": "Beta Customer", "division_id": div_b["id"]},
    ).json()

    _make_accountant(c, admin_h, SessionLocal, email="custscope@x.com", division_id=div_a["id"])
    acc_h = _login(c, "custscope@x.com")
    rows = c.get("/api/v1/masters/customers", headers=acc_h).json()
    ids = {r["id"] for r in rows}
    assert cust_a["id"] in ids
    assert cust_b["id"] not in ids


# ============================== Edit window ==============================
_DRAFT_SEQ = [0]


def _make_draft_case_as_accountant(c, h, *, admin_for_seed=None):
    """Build a draft case visible to ``h``.

    Customer creation needs ``masters:write`` which the Accountant
    role doesn't have - so when an admin header is supplied we
    seed the customer through it. Otherwise we reuse ``h``
    (which is what the admin-doubling-as-Accountant calls do).
    """
    seed_h = admin_for_seed or h
    div_id = c.get("/api/v1/masters/divisions", headers=h).json()[0]["id"]
    banks = c.get("/api/v1/masters/banks", headers=h).json()
    _DRAFT_SEQ[0] += 1
    code = f"P39EW-{_DRAFT_SEQ[0]:03d}"
    cust = c.post(
        "/api/v1/masters/customers",
        headers=seed_h,
        json={"code": code, "name": f"Edit Window Co {code}", "division_id": div_id},
    ).json()
    case = c.post(
        "/api/v1/cases",
        headers=h,
        json={
            "customer_id": cust["id"],
            "division_id": div_id,
            "is_civil": True,
            "actual_due_amount": "45000",
            "legal_filing_amount": "50000",
            "cheques": [
                {
                    "cheque_number": "EW-1",
                    "bank_id": banks[0]["id"],
                    "amount": "45000",
                    "cheque_date": "2026-05-15",
                    "cheque_type": "Normal",
                    "bounce_reason": "Insufficient Funds",
                }
            ],
        },
    ).json()
    return case


def test_accountant_can_edit_after_submit_while_at_sales_manager(client) -> None:
    """Phase 39: the case stays editable for the creator while it's
    Submitted at Sales Manager. Once SM acts, edits lock.

    Uses a non-super Accountant + a separate non-super Sales
    Manager so the ``is_super`` bypass on update_case doesn't
    mask the edit-window rule we're trying to exercise.
    """
    c, SessionLocal = client
    admin_h = _admin_h(c)

    div_id = c.get("/api/v1/masters/divisions", headers=admin_h).json()[0]["id"]
    _make_accountant(
        c, admin_h, SessionLocal, email="acct39@x.com", division_id=div_id
    )
    # Sales Manager account so we can approve from the right user.
    roles = c.get("/api/v1/roles", headers=admin_h).json()
    sm_role = next(r["id"] for r in roles if r["name"] == "Sales Manager")
    sm = c.post(
        "/api/v1/users",
        headers=admin_h,
        json={
            "email": "sm39@x.com",
            "full_name": "SM",
            "password": "Pa55word!",
            "role_id": sm_role,
            "is_active": True,
            "is_super": False,
            "is_all_divisions": False,
            "division_ids": [div_id],
        },
    )
    assert sm.status_code == 201, sm.text

    acc_h = _login(c, "acct39@x.com")
    case = _make_draft_case_as_accountant(c, acc_h, admin_for_seed=admin_h)
    case_id = case["id"]

    sub = c.post(f"/api/v1/cases/{case_id}/submit", headers=acc_h)
    assert sub.status_code == 200, sub.text
    body = sub.json()
    assert body["status"] == "Submitted"
    assert body["current_stage"] == "Sales Manager"

    # PATCH while at Sales Manager - should succeed.
    patched = c.patch(
        f"/api/v1/cases/{case_id}",
        headers=acc_h,
        json={"commands": "Fixed a typo after submission"},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["commands"] == "Fixed a typo after submission"

    # SM approves -> case now at Division Manager.
    sm_h = _login(c, "sm39@x.com")
    approve = c.post(
        f"/api/v1/cases/{case_id}/transition",
        headers=sm_h,
        json={"action": "approve", "comment": "ok"},
    )
    assert approve.status_code == 200, approve.text

    # Further PATCH by the Accountant must be refused.
    blocked = c.patch(
        f"/api/v1/cases/{case_id}",
        headers=acc_h,
        json={"commands": "Trying to edit after SM acted"},
    )
    assert blocked.status_code == 400, blocked.text
    assert "no longer editable" in blocked.json()["detail"].lower()


def test_attachment_upload_works_after_submit(client) -> None:
    """Phase 39: a renewed CR Copy can be attached at any time
    while the case isn't Closed/Rejected."""
    c, _ = client
    h = _admin_h(c)
    case = _make_draft_case_as_accountant(c, h)
    case_id = case["id"]
    c.post(f"/api/v1/cases/{case_id}/submit", headers=h)
    # Approve all the way through to Filed status? Actually just
    # uploading post-submit is enough to prove the gate doesn't bite.
    r = c.post(
        f"/api/v1/cases/{case_id}/attachments",
        headers=h,
        files={"file": ("cr.pdf", b"%PDF-CR", "application/pdf")},
        data={"category": "CR Copy"},
    )
    assert r.status_code == 201, r.text


# ============================== Closure discount ==============================
def test_closure_round_trip_records_discount(client) -> None:
    """Phase 39: the closure carries an explicit discount_amount
    and the API round-trips it. Final settled = actual_due - discount
    is the operator's responsibility (the UI does it); the API
    just persists both fields verbatim so reports can show them."""
    c, SessionLocal = client
    h = _admin_h(c)
    case = _make_draft_case_as_accountant(c, h)
    case_id = case["id"]

    # Walk the case through to Approved so it becomes closable.
    c.post(f"/api/v1/cases/{case_id}/submit", headers=h)
    for _ in range(6):  # 6 approval stages
        r = c.post(
            f"/api/v1/cases/{case_id}/transition",
            headers=h,
            json={"action": "approve", "comment": "ok"},
        )
        assert r.status_code == 200, r.text

    body = c.get(f"/api/v1/cases/{case_id}", headers=h).json()
    assert body["status"] == "Approved"

    # Close with a discount.
    close = c.post(
        f"/api/v1/cases/{case_id}/close",
        headers=h,
        json={
            "closure_type": "cash_received",
            "command": "Settled in cash with 5k discount",
            "settled_amount": "40000",
            "discount_amount": "5000",
            "settled_date": "2026-07-01",
            "cash_receipt_no": "CRN-39",
        },
    )
    assert close.status_code == 201, close.text
    closure = close.json()
    assert closure["settled_amount"] == "40000.00"
    assert closure["discount_amount"] == "5000.00"

    # GET round-trip
    fetched = c.get(f"/api/v1/cases/{case_id}/closure", headers=h).json()
    assert fetched["settled_amount"] == "40000.00"
    assert fetched["discount_amount"] == "5000.00"


def test_closure_discount_defaults_to_zero(client) -> None:
    """Existing call sites that don't send discount_amount keep
    working - the field defaults to 0."""
    c, SessionLocal = client
    h = _admin_h(c)
    case = _make_draft_case_as_accountant(c, h)
    case_id = case["id"]
    c.post(f"/api/v1/cases/{case_id}/submit", headers=h)
    for _ in range(6):
        c.post(
            f"/api/v1/cases/{case_id}/transition",
            headers=h,
            json={"action": "approve", "comment": "ok"},
        )

    close = c.post(
        f"/api/v1/cases/{case_id}/close",
        headers=h,
        json={
            "closure_type": "cash_received",
            "command": "No discount path",
            "settled_amount": "45000",
            "settled_date": "2026-07-01",
            "cash_receipt_no": "CRN-39-2",
        },
    )
    assert close.status_code == 201, close.text
    assert close.json()["discount_amount"] == "0.00"
