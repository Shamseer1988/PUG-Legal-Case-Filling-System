"""Phase 19: approval-comment attachments stage + bind on transition."""

import io

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import *  # noqa: F401,F403
from app.models.case import CaseTransitionAttachment
from app.models.masters import Customer
from app.models.user import Role, User, UserDivisionMap
from app.services.seed import DEFAULT_ADMIN_EMAIL, DEFAULT_ADMIN_PASSWORD, run_seed


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "p19.db"
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


def _admin_headers(c: TestClient) -> dict[str, str]:
    r = c.post(
        "/api/v1/auth/login",
        json={"email": DEFAULT_ADMIN_EMAIL, "password": DEFAULT_ADMIN_PASSWORD},
    )
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _submit_case(c: TestClient, h: dict[str, str]) -> int:
    divs = c.get("/api/v1/masters/divisions", headers=h).json()
    div_id = divs[0]["id"]
    banks = c.get("/api/v1/masters/banks", headers=h).json()
    r = c.post(
        "/api/v1/masters/customers",
        headers=h,
        json={"code": "CT19", "name": "Acme19", "division_id": div_id},
    )
    cust_id = r.json()["id"]
    r = c.post(
        "/api/v1/cases",
        headers=h,
        json={
            "customer_id": cust_id,
            "division_id": div_id,
            "is_civil": True,
            "cheques": [
                {
                    "cheque_number": "CH-19-1",
                    "bank_id": banks[0]["id"],
                    "amount": "1000.00",
                    "cheque_date": "2026-05-15",
                    "cheque_type": "Normal",
                    "bounce_reason": "Funds",
                },
            ],
        },
    )
    case_id = r.json()["id"]
    r = c.post(f"/api/v1/cases/{case_id}/submit", headers=h)
    assert r.status_code == 200, r.text
    return case_id


def test_upload_then_bind_attachment_on_approve(client) -> None:
    c, _ = client
    h = _admin_headers(c)
    case_id = _submit_case(c, h)

    # Pre-upload an attachment
    r = c.post(
        f"/api/v1/cases/{case_id}/transition-attachments",
        headers=h,
        files={"file": ("evidence.pdf", io.BytesIO(b"%PDF-fake"), "application/pdf")},
    )
    assert r.status_code == 201, r.text
    att = r.json()
    assert att["transition_id"] is None  # unbound
    att_id = att["id"]

    # Approve and bind
    r = c.post(
        f"/api/v1/cases/{case_id}/transition",
        headers=h,
        json={"action": "approve", "comment": "Looks good", "attachment_ids": [att_id]},
    )
    assert r.status_code == 200, r.text

    # Timeline should now show the attachment under the latest entry
    tl = c.get(f"/api/v1/cases/{case_id}/timeline", headers=h).json()
    assert tl, "timeline missing"
    latest = tl[-1]
    assert latest["action_type"] == "approve"
    assert len(latest["attachments"]) == 1
    assert latest["attachments"][0]["id"] == att_id
    assert latest["attachments"][0]["transition_id"] == latest["id"]
    assert latest["attachments"][0]["original_filename"] == "evidence.pdf"
    assert latest["attachments"][0]["uploaded_by_name"]  # has a name

    # Download the bound file
    r = c.get(
        f"/api/v1/cases/{case_id}/transition-attachments/{att_id}/download",
        headers=h,
    )
    assert r.status_code == 200
    assert r.content == b"%PDF-fake"


def test_transition_rejects_unknown_attachment_id(client) -> None:
    c, _ = client
    h = _admin_headers(c)
    case_id = _submit_case(c, h)
    r = c.post(
        f"/api/v1/cases/{case_id}/transition",
        headers=h,
        json={"action": "approve", "comment": "x", "attachment_ids": [9999]},
    )
    assert r.status_code == 400
    assert "unknown" in r.json()["detail"].lower() or "bound" in r.json()["detail"].lower()


def test_transition_rejects_already_bound_attachment(client) -> None:
    c, _ = client
    h = _admin_headers(c)
    case_id = _submit_case(c, h)

    # Upload + bind via first approve
    up = c.post(
        f"/api/v1/cases/{case_id}/transition-attachments",
        headers=h,
        files={"file": ("a.txt", io.BytesIO(b"x"), "text/plain")},
    ).json()
    c.post(
        f"/api/v1/cases/{case_id}/transition",
        headers=h,
        json={"action": "approve", "attachment_ids": [up["id"]]},
    )

    # Try to bind again at the next stage
    r = c.post(
        f"/api/v1/cases/{case_id}/transition",
        headers=h,
        json={"action": "approve", "attachment_ids": [up["id"]]},
    )
    assert r.status_code == 400


def test_delete_unbound_attachment_works_bound_attachment_locked(client) -> None:
    c, _ = client
    h = _admin_headers(c)
    case_id = _submit_case(c, h)
    up = c.post(
        f"/api/v1/cases/{case_id}/transition-attachments",
        headers=h,
        files={"file": ("draft.txt", io.BytesIO(b"x"), "text/plain")},
    ).json()
    # Unbound: delete works
    r = c.delete(
        f"/api/v1/cases/{case_id}/transition-attachments/{up['id']}",
        headers=h,
    )
    assert r.status_code == 204

    # Re-upload + bind
    up2 = c.post(
        f"/api/v1/cases/{case_id}/transition-attachments",
        headers=h,
        files={"file": ("final.txt", io.BytesIO(b"y"), "text/plain")},
    ).json()
    c.post(
        f"/api/v1/cases/{case_id}/transition",
        headers=h,
        json={"action": "approve", "attachment_ids": [up2["id"]]},
    )
    # Bound: deletion blocked so audit trail stays intact
    r = c.delete(
        f"/api/v1/cases/{case_id}/transition-attachments/{up2['id']}",
        headers=h,
    )
    assert r.status_code == 400


def test_transition_without_attachments_still_works(client) -> None:
    """Phase 19 must not regress the pre-existing transition flow."""
    c, _ = client
    h = _admin_headers(c)
    case_id = _submit_case(c, h)
    r = c.post(
        f"/api/v1/cases/{case_id}/transition",
        headers=h,
        json={"action": "approve", "comment": "no files"},
    )
    assert r.status_code == 200
    tl = c.get(f"/api/v1/cases/{case_id}/timeline", headers=h).json()
    assert tl[-1]["attachments"] == []


def test_attachment_endpoints_require_auth(client) -> None:
    c, _ = client
    assert c.post(
        "/api/v1/cases/1/transition-attachments",
        files={"file": ("x.txt", io.BytesIO(b""), "text/plain")},
    ).status_code == 401
    assert c.get("/api/v1/cases/1/transition-attachments/1/download").status_code == 401
