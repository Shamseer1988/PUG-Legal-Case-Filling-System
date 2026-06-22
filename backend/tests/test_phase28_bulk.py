"""Phase 28: bulk transitions on the approvals inbox + bulk
signatory reassignment by admin."""

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
    db_path = tmp_path / "p28.db"
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
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _make_user(SessionLocal, email: str, role_name: str, division_id: int | None = None) -> int:
    db = SessionLocal()
    try:
        role = db.query(Role).filter(Role.name == role_name).first()
        u = User(
            email=email,
            password_hash=hash_password("Pass@1234"),
            full_name=role_name,
            role_id=role.id,
        )
        db.add(u)
        db.flush()
        if division_id is not None:
            db.add(UserDivisionMap(user_id=u.id, division_id=division_id))
        db.commit()
        return u.id
    finally:
        db.close()


def _submit_case(c: TestClient, h: dict[str, str], sm_id: int | None = None) -> tuple[int, int]:
    """Create + submit a case. Returns (case_id, division_id)."""
    divs = c.get("/api/v1/masters/divisions", headers=h).json()
    div_id = divs[0]["id"]
    banks = c.get("/api/v1/masters/banks", headers=h).json()
    import uuid as _u

    cust = c.post(
        "/api/v1/masters/customers",
        headers=h,
        json={
            "code": f"C{_u.uuid4().hex[:6]}",
            "name": f"Acme {_u.uuid4().hex[:4]}",
            "division_id": div_id,
        },
    ).json()
    payload = {
        "customer_id": cust["id"],
        "division_id": div_id,
        "is_civil": True,
        "cheques": [
            {
                "cheque_number": f"CH-{_u.uuid4().hex[:6]}",
                "bank_id": banks[0]["id"],
                "amount": "100.00",
                "cheque_date": "2026-05-15",
                "cheque_type": "Normal",
                "bounce_reason": "Funds",
            },
        ],
    }
    if sm_id:
        payload["sales_manager_id"] = sm_id
    case_id = c.post("/api/v1/cases", headers=h, json=payload).json()["id"]
    c.post(f"/api/v1/cases/{case_id}/submit", headers=h)
    return case_id, div_id


# ---------------- bulk transition ----------------
def test_bulk_approve_promotes_multiple_cases(client) -> None:
    c, _ = client
    h = _admin_h(c)
    ids = [ _submit_case(c, h)[0] for _ in range(3) ]

    r = c.post(
        "/api/v1/approvals/bulk-transition",
        headers=h,
        json={"case_ids": ids, "action": "approve", "comment": "looks good"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["succeeded"] == 3
    assert body["failed"] == 0
    # Each case advanced
    for cid in ids:
        case = c.get(f"/api/v1/cases/{cid}", headers=h).json()
        assert case["status"] != "Submitted", "case should have moved past Submitted"


def test_bulk_reject_requires_comment(client) -> None:
    c, _ = client
    h = _admin_h(c)
    ids = [_submit_case(c, h)[0]]
    r = c.post(
        "/api/v1/approvals/bulk-transition",
        headers=h,
        json={"case_ids": ids, "action": "reject", "comment": ""},
    )
    assert r.status_code == 400


def test_bulk_partial_failure_reports_per_row(client) -> None:
    """Mix one good case with one out-of-scope id - the good one
    succeeds, the bad one is reported as failed."""
    c, _ = client
    h = _admin_h(c)
    good_id, _ = _submit_case(c, h)
    bad_id = 999_999

    r = c.post(
        "/api/v1/approvals/bulk-transition",
        headers=h,
        json={"case_ids": [good_id, bad_id], "action": "approve", "comment": ""},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["succeeded"] == 1
    assert body["failed"] == 1
    by_id = {item["case_id"]: item for item in body["items"]}
    assert by_id[good_id]["ok"] is True
    assert by_id[bad_id]["ok"] is False
    assert "scope" in by_id[bad_id]["detail"].lower() or "not found" in by_id[bad_id]["detail"].lower()


def test_bulk_skips_unauthorised_user(client) -> None:
    """A Sales Manager bulk-approving a case waiting at the Division
    Manager stage should be reported as 'Not authorised', not crash
    the batch."""
    c, SessionLocal = client
    admin_h = _admin_h(c)
    case_id, div_id = _submit_case(c, admin_h)
    # Move the case past the Sales Manager stage so SM no longer
    # has authority on it.
    c.post(
        f"/api/v1/cases/{case_id}/transition",
        headers=admin_h,
        json={"action": "approve", "comment": "by admin"},
    )

    _make_user(SessionLocal, "sm@pug.local", "Sales Manager", division_id=div_id)
    sm_h = _login(c, "sm@pug.local")
    r = c.post(
        "/api/v1/approvals/bulk-transition",
        headers=sm_h,
        json={"case_ids": [case_id], "action": "approve", "comment": ""},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["failed"] == 1
    assert "Not authorised" in body["items"][0]["detail"]


def test_bulk_dedupes_case_ids(client) -> None:
    c, _ = client
    h = _admin_h(c)
    cid, _ = _submit_case(c, h)
    r = c.post(
        "/api/v1/approvals/bulk-transition",
        headers=h,
        json={"case_ids": [cid, cid, cid], "action": "approve", "comment": ""},
    )
    assert r.status_code == 200
    # Dedup: only one row, with succeeded=1
    body = r.json()
    assert body["succeeded"] == 1
    assert len(body["items"]) == 1


def test_bulk_transition_requires_auth(client) -> None:
    c, _ = client
    r = c.post(
        "/api/v1/approvals/bulk-transition",
        json={"case_ids": [1], "action": "approve", "comment": ""},
    )
    assert r.status_code == 401


# ---------------- bulk reassign ----------------
def test_bulk_reassign_moves_sales_manager(client) -> None:
    c, SessionLocal = client
    h = _admin_h(c)
    sm_old = _make_user(SessionLocal, "sm-old@pug.local", "Sales Manager")
    sm_new = _make_user(SessionLocal, "sm-new@pug.local", "Sales Manager")

    case_a, _ = _submit_case(c, h, sm_id=sm_old)
    case_b, _ = _submit_case(c, h, sm_id=sm_old)
    case_c, _ = _submit_case(c, h, sm_id=sm_new)  # already on new SM

    r = c.post(
        "/api/v1/admin/cases/bulk-reassign",
        headers=h,
        json={
            "user_field": "sales_manager_id",
            "from_user_id": sm_old,
            "to_user_id": sm_new,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["updated"] == 2  # only the two cases that pointed at sm_old
    assert body["skipped_closed"] == 0

    db = SessionLocal()
    try:
        a = db.get(Case, case_a)
        b = db.get(Case, case_b)
        co = db.get(Case, case_c)
        assert a.sales_manager_id == sm_new
        assert b.sales_manager_id == sm_new
        assert co.sales_manager_id == sm_new  # unchanged
    finally:
        db.close()


def test_bulk_reassign_skips_closed_when_only_open(client) -> None:
    c, SessionLocal = client
    h = _admin_h(c)
    sm_old = _make_user(SessionLocal, "smo@pug.local", "Sales Manager")
    sm_new = _make_user(SessionLocal, "smn@pug.local", "Sales Manager")
    case_open, _ = _submit_case(c, h, sm_id=sm_old)
    case_closed, _ = _submit_case(c, h, sm_id=sm_old)
    db = SessionLocal()
    try:
        db.get(Case, case_closed).status = "Closed"
        db.commit()
    finally:
        db.close()

    r = c.post(
        "/api/v1/admin/cases/bulk-reassign",
        headers=h,
        json={
            "user_field": "sales_manager_id",
            "from_user_id": sm_old,
            "to_user_id": sm_new,
            "only_open": True,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["updated"] == 1
    assert body["skipped_closed"] == 1


def test_bulk_reassign_rejects_same_user(client) -> None:
    c, SessionLocal = client
    h = _admin_h(c)
    sm = _make_user(SessionLocal, "sms@pug.local", "Sales Manager")
    r = c.post(
        "/api/v1/admin/cases/bulk-reassign",
        headers=h,
        json={
            "user_field": "sales_manager_id",
            "from_user_id": sm,
            "to_user_id": sm,
        },
    )
    assert r.status_code == 400


def test_bulk_reassign_rejects_inactive_target(client) -> None:
    c, SessionLocal = client
    h = _admin_h(c)
    src = _make_user(SessionLocal, "active@pug.local", "Sales Manager")
    dst = _make_user(SessionLocal, "deactivated@pug.local", "Sales Manager")
    db = SessionLocal()
    try:
        db.get(User, dst).is_active = False
        db.commit()
    finally:
        db.close()
    r = c.post(
        "/api/v1/admin/cases/bulk-reassign",
        headers=h,
        json={
            "user_field": "sales_manager_id",
            "from_user_id": src,
            "to_user_id": dst,
        },
    )
    assert r.status_code == 400


def test_bulk_reassign_requires_users_write(client) -> None:
    c, SessionLocal = client
    _make_user(SessionLocal, "audit@pug.local", "Auditor")
    audit_h = _login(c, "audit@pug.local")
    r = c.post(
        "/api/v1/admin/cases/bulk-reassign",
        headers=audit_h,
        json={
            "user_field": "sales_manager_id",
            "from_user_id": 1,
            "to_user_id": 2,
        },
    )
    assert r.status_code == 403


def test_bulk_reassign_rejects_unknown_user_field(client) -> None:
    c, _ = client
    h = _admin_h(c)
    r = c.post(
        "/api/v1/admin/cases/bulk-reassign",
        headers=h,
        json={
            "user_field": "evil_drop_table",
            "from_user_id": 1,
            "to_user_id": 2,
        },
    )
    assert r.status_code == 422
