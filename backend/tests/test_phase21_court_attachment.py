"""Phase 21: court-filing acknowledgement attachment upload + delete."""

import io

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import *  # noqa: F401,F403
from app.models.case import CASE_STATUS_APPROVED, Case, STAGE_LAWYER
from app.services.seed import DEFAULT_ADMIN_EMAIL, DEFAULT_ADMIN_PASSWORD, run_seed


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "p21.db"
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


def _make_approved_case_with_filing(c: TestClient, h: dict[str, str], SessionLocal) -> tuple[int, int]:
    """Returns (case_id, filing_id) — case advanced to Approved/Lawyer
    via a direct DB nudge to avoid walking the whole approval chain."""
    divs = c.get("/api/v1/masters/divisions", headers=h).json()
    div_id = divs[0]["id"]
    banks = c.get("/api/v1/masters/banks", headers=h).json()
    cust = c.post(
        "/api/v1/masters/customers",
        headers=h,
        json={"code": "CT21", "name": "Acme21", "division_id": div_id},
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
                    "cheque_number": "CH-21-1",
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

    db = SessionLocal()
    try:
        case_row = db.get(Case, case_id)
        case_row.status = CASE_STATUS_APPROVED
        case_row.current_stage = STAGE_LAWYER
        db.commit()
    finally:
        db.close()

    # Now record the court filing
    r = c.post(
        f"/api/v1/cases/{case_id}/court-filing",
        headers=h,
        json={
            "police_case_no": "PC-21",
            "court_case_no": "CC-21",
            "filed_court": "City Court",
            "filed_date": "2026-06-01",
            "notes": "Filed today",
        },
    )
    assert r.status_code == 201, r.text
    return case_id, r.json()["id"]


def test_upload_acknowledgement_attaches_and_returns_filename(client) -> None:
    c, SessionLocal = client
    h = _admin_h(c)
    case_id, _ = _make_approved_case_with_filing(c, h, SessionLocal)

    # No attachment yet
    f = c.get(f"/api/v1/cases/{case_id}/court-filing", headers=h).json()
    assert f["acknowledgment_attachment_id"] is None
    assert f["acknowledgment_attachment_filename"] == ""

    payload = b"%PDF-acknowledgement"
    r = c.post(
        f"/api/v1/cases/{case_id}/court-filing/attachment",
        headers=h,
        files={"file": ("ack.pdf", io.BytesIO(payload), "application/pdf")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["acknowledgment_attachment_id"]
    assert body["acknowledgment_attachment_filename"] == "ack.pdf"
    assert body["acknowledgment_attachment_size"] == len(payload)

    # The file is now downloadable via the existing case-attachment endpoint
    att_id = body["acknowledgment_attachment_id"]
    r = c.get(
        f"/api/v1/cases/{case_id}/attachments/{att_id}/download",
        headers=h,
    )
    assert r.status_code == 200
    assert r.content == payload


def test_upload_acknowledgement_replaces_previous(client) -> None:
    c, SessionLocal = client
    h = _admin_h(c)
    case_id, _ = _make_approved_case_with_filing(c, h, SessionLocal)

    first = c.post(
        f"/api/v1/cases/{case_id}/court-filing/attachment",
        headers=h,
        files={"file": ("old.pdf", io.BytesIO(b"OLD"), "application/pdf")},
    ).json()
    second = c.post(
        f"/api/v1/cases/{case_id}/court-filing/attachment",
        headers=h,
        files={"file": ("new.pdf", io.BytesIO(b"NEW-bigger"), "application/pdf")},
    ).json()

    assert first["acknowledgment_attachment_id"] != second["acknowledgment_attachment_id"]
    assert second["acknowledgment_attachment_filename"] == "new.pdf"

    # Old attachment row should be gone
    r = c.get(
        f"/api/v1/cases/{case_id}/attachments/{first['acknowledgment_attachment_id']}/download",
        headers=h,
    )
    assert r.status_code == 404


def test_upload_acknowledgement_rejected_without_filing(client) -> None:
    """Phase 21 makes uploading the file depend on the filing existing -
    you can't attach evidence to something that hasn't been recorded yet."""
    c, SessionLocal = client
    h = _admin_h(c)
    # Approved case but no court filing recorded yet
    divs = c.get("/api/v1/masters/divisions", headers=h).json()
    div_id = divs[0]["id"]
    banks = c.get("/api/v1/masters/banks", headers=h).json()
    cust = c.post(
        "/api/v1/masters/customers",
        headers=h,
        json={"code": "CT21B", "name": "Pending21", "division_id": div_id},
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
                    "cheque_number": "CH-21-2",
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
    db = SessionLocal()
    try:
        case_row = db.get(Case, case_id)
        case_row.status = CASE_STATUS_APPROVED
        case_row.current_stage = STAGE_LAWYER
        db.commit()
    finally:
        db.close()

    r = c.post(
        f"/api/v1/cases/{case_id}/court-filing/attachment",
        headers=h,
        files={"file": ("ack.pdf", io.BytesIO(b"x"), "application/pdf")},
    )
    assert r.status_code == 400


def test_delete_acknowledgement_clears_link_and_file(client) -> None:
    c, SessionLocal = client
    h = _admin_h(c)
    case_id, _ = _make_approved_case_with_filing(c, h, SessionLocal)
    body = c.post(
        f"/api/v1/cases/{case_id}/court-filing/attachment",
        headers=h,
        files={"file": ("ack.pdf", io.BytesIO(b"x"), "application/pdf")},
    ).json()
    att_id = body["acknowledgment_attachment_id"]

    r = c.delete(f"/api/v1/cases/{case_id}/court-filing/attachment", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["acknowledgment_attachment_id"] is None
    assert body["acknowledgment_attachment_filename"] == ""

    # Idempotent - second delete is a no-op
    r = c.delete(f"/api/v1/cases/{case_id}/court-filing/attachment", headers=h)
    assert r.status_code == 200
    # Downloading the orphaned attachment id should now 404
    assert (
        c.get(
            f"/api/v1/cases/{case_id}/attachments/{att_id}/download",
            headers=h,
        ).status_code
        == 404
    )


def test_attachment_endpoints_require_cases_file(client) -> None:
    c, _ = client
    # No auth at all
    assert c.post(
        "/api/v1/cases/1/court-filing/attachment",
        files={"file": ("x", io.BytesIO(b""), "application/pdf")},
    ).status_code == 401
    assert (
        c.delete("/api/v1/cases/1/court-filing/attachment").status_code == 401
    )
