"""Phase 41: physical-document chain of custody.

Covers
- Document Location master CRUD
- PhysicalDocument register / patch / retire round-trip
- Custody log appends on register and transfer
- Validation: empty destination rejected
- ``current_*`` snapshot mirrors the latest log row
- Permissions: ``documents:transfer`` required for write paths
- Division scoping: cross-division calls 404
- "with-me" and "overdue" reports
- Print view: physical files appendix shows up
- Signature upload + view
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import *  # noqa: F401,F403
from app.models.physical_document import DocumentCustodyLog, PhysicalDocument
from app.services.seed import (
    DEFAULT_ADMIN_EMAIL,
    DEFAULT_ADMIN_PASSWORD,
    run_seed,
)

from tests.conftest import attach_default_signatory


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "p41.db"
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


_P41_SEQ = [0]


def _next_code(prefix: str) -> str:
    _P41_SEQ[0] += 1
    return f"{prefix}-{_P41_SEQ[0]:03d}"


def _make_division(c, h, *, code: str | None = None) -> dict:
    return c.post(
        "/api/v1/masters/divisions",
        headers=h,
        json={"code": code or _next_code("DIV"), "name": "Test Div"},
    ).json()


def _make_customer(c, h, *, division_id: int) -> dict:
    return c.post(
        "/api/v1/masters/customers",
        headers=h,
        json={
            "code": _next_code("CUS"),
            "name": "Test Cust",
            "division_id": division_id,
        },
    ).json()


def _make_case(c, h, *, division_id: int) -> dict:
    cust = _make_customer(c, h, division_id=division_id)
    case = c.post(
        "/api/v1/cases",
        headers=h,
        json={
            "customer_id": cust["id"],
            "division_id": division_id,
            "customer_type": "Retail",
            "actual_due_amount": "100",
            "legal_filing_amount": "100",
        },
    ).json()
    return case


def _make_user_with_role(c, h, *, role_name: str, email: str) -> dict:
    role = next(
        r for r in c.get("/api/v1/roles", headers=h).json() if r["name"] == role_name
    )
    return c.post(
        "/api/v1/users",
        headers=h,
        json={
            "email": email,
            "full_name": email.split("@")[0],
            "role_id": role["id"],
            "password": "Passw0rd!",
            "division_ids": [],
        },
    ).json()


def _login(c, email: str) -> dict[str, str]:
    r = c.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Passw0rd!"},
    )
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# ============================== Document Locations master ==============================
def test_document_location_master_crud(client) -> None:
    c, _ = client
    h = _admin_h(c)

    created = c.post(
        "/api/v1/masters/document-locations",
        headers=h,
        json={
            "code": "SAFE-A",
            "name": "Cabinet A-3",
            "description": "Behind reception desk",
            "is_storage": True,
        },
    )
    assert created.status_code == 201, created.text
    loc = created.json()
    assert loc["is_storage"] is True

    listed = c.get("/api/v1/masters/document-locations", headers=h).json()
    assert any(r["id"] == loc["id"] for r in listed)

    patched = c.patch(
        f"/api/v1/masters/document-locations/{loc['id']}",
        headers=h,
        json={"is_storage": False, "description": "Moved to lawyer's office"},
    )
    assert patched.status_code == 200
    assert patched.json()["is_storage"] is False


# ============================== Register + log head ==============================
def test_register_creates_initial_log_entry(client) -> None:
    c, _ = client
    h = _admin_h(c)
    div = _make_division(c, h)
    case = _make_case(c, h, division_id=div["id"])
    loc = c.post(
        "/api/v1/masters/document-locations",
        headers=h,
        json={"code": _next_code("LOC"), "name": "Cabinet", "is_storage": True},
    ).json()

    resp = c.post(
        f"/api/v1/cases/{case['id']}/documents",
        headers=h,
        json={
            "label": "Original Cheque #00123",
            "kind": "original_cheque",
            "initial_location_id": loc["id"],
            "initial_note": "On registration",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["label"] == "Original Cheque #00123"
    assert body["case_id"] == case["id"]
    assert body["current_location_id"] == loc["id"]
    assert body["current_location_name"] == "Cabinet"
    assert len(body["custody_log"]) == 1
    head = body["custody_log"][0]
    assert head["from_user_id"] is None
    assert head["location_id"] == loc["id"]
    assert head["note"] == "On registration"


# ============================== Transfer flow ==============================
def test_transfer_appends_log_and_snapshots(client) -> None:
    c, _ = client
    h = _admin_h(c)
    div = _make_division(c, h)
    case = _make_case(c, h, division_id=div["id"])
    storage_loc = c.post(
        "/api/v1/masters/document-locations",
        headers=h,
        json={"code": _next_code("LOC"), "name": "Storage", "is_storage": True},
    ).json()

    # Register and immediately park in storage.
    doc = c.post(
        f"/api/v1/cases/{case['id']}/documents",
        headers=h,
        json={
            "label": "ID Copy",
            "kind": "id_copy",
            "initial_location_id": storage_loc["id"],
        },
    ).json()
    assert len(doc["custody_log"]) == 1

    # Hand off to a lawyer-type user.
    lawyer = _make_user_with_role(c, h, role_name="Lawyer", email="phys-lawyer@x.com")
    transfer = c.post(
        f"/api/v1/documents/{doc['id']}/transfer",
        headers=h,
        json={
            "to_user_id": lawyer["id"],
            "note": "Filing tomorrow at court",
        },
    )
    assert transfer.status_code == 200, transfer.text
    after = transfer.json()
    assert after["current_holder_user_id"] == lawyer["id"]
    assert after["current_holder_name"] == lawyer["full_name"]
    assert after["current_location_id"] is None
    assert len(after["custody_log"]) == 2
    # Log rows ordered newest-first.
    newest = after["custody_log"][0]
    assert newest["from_user_id"] is None  # storage row had no holder
    assert newest["to_user_id"] == lawyer["id"]
    assert newest["note"] == "Filing tomorrow at court"


def test_transfer_rejects_empty_destination(client) -> None:
    c, _ = client
    h = _admin_h(c)
    div = _make_division(c, h)
    case = _make_case(c, h, division_id=div["id"])
    doc = c.post(
        f"/api/v1/cases/{case['id']}/documents",
        headers=h,
        json={"label": "Bare doc"},
    ).json()

    r = c.post(
        f"/api/v1/documents/{doc['id']}/transfer",
        headers=h,
        json={},  # no recipient, no location, no text
    )
    assert r.status_code == 422
    assert "destination" in r.json()["detail"].lower() or "recipient" in r.json()["detail"].lower()


def test_transfer_rejects_unknown_location(client) -> None:
    c, _ = client
    h = _admin_h(c)
    div = _make_division(c, h)
    case = _make_case(c, h, division_id=div["id"])
    doc = c.post(
        f"/api/v1/cases/{case['id']}/documents",
        headers=h,
        json={"label": "Bare doc"},
    ).json()
    r = c.post(
        f"/api/v1/documents/{doc['id']}/transfer",
        headers=h,
        json={"to_location_id": 99999},
    )
    assert r.status_code == 422


# ============================== Reports ==============================
def test_files_with_me_only_returns_active_holdings(client) -> None:
    c, _ = client
    h_admin = _admin_h(c)
    div = _make_division(c, h_admin)
    case = _make_case(c, h_admin, division_id=div["id"])

    accountant = _make_user_with_role(
        c, h_admin, role_name="Accountant", email="phys-acc@x.com"
    )
    h_acc = _login(c, "phys-acc@x.com")

    # Admin registers two docs and hands one to the Accountant.
    d1 = c.post(
        f"/api/v1/cases/{case['id']}/documents",
        headers=h_admin,
        json={"label": "Doc-A"},
    ).json()
    d2 = c.post(
        f"/api/v1/cases/{case['id']}/documents",
        headers=h_admin,
        json={"label": "Doc-B"},
    ).json()
    c.post(
        f"/api/v1/documents/{d1['id']}/transfer",
        headers=h_admin,
        json={"to_user_id": accountant["id"]},
    )

    mine = c.get("/api/v1/documents/reports/with-me", headers=h_acc).json()
    labels = {row["label"] for row in mine}
    assert "Doc-A" in labels
    assert "Doc-B" not in labels


def test_overdue_skips_documents_parked_in_storage(client) -> None:
    c, S = client
    h = _admin_h(c)
    div = _make_division(c, h)
    case = _make_case(c, h, division_id=div["id"])
    storage_loc = c.post(
        "/api/v1/masters/document-locations",
        headers=h,
        json={"code": _next_code("LOC"), "name": "Storage", "is_storage": True},
    ).json()
    accountant = _make_user_with_role(
        c, h, role_name="Accountant", email="phys-acc2@x.com"
    )

    # In-storage doc: should NOT show up regardless of age.
    parked = c.post(
        f"/api/v1/cases/{case['id']}/documents",
        headers=h,
        json={
            "label": "Parked",
            "initial_location_id": storage_loc["id"],
        },
    ).json()

    # Out-of-office doc: hand to a user, then back-date the transfer
    # so it looks 30 days old.
    held = c.post(
        f"/api/v1/cases/{case['id']}/documents",
        headers=h,
        json={"label": "Held"},
    ).json()
    c.post(
        f"/api/v1/documents/{held['id']}/transfer",
        headers=h,
        json={"to_user_id": accountant["id"]},
    )

    # Back-date the latest log + the snapshot directly via the DB
    # so we don't have to wait 8 real days for the report to fire.
    with S() as db:
        doc = db.get(PhysicalDocument, held["id"])
        old = datetime.utcnow() - timedelta(days=30)
        doc.last_transferred_at = old
        latest = (
            db.query(DocumentCustodyLog)
            .filter(DocumentCustodyLog.document_id == doc.id)
            .order_by(DocumentCustodyLog.id.desc())
            .first()
        )
        latest.transferred_at = old
        db.commit()

    overdue = c.get("/api/v1/documents/reports/overdue?days=7", headers=h).json()
    labels = {row["label"] for row in overdue}
    assert "Held" in labels
    assert "Parked" not in labels


# ============================== Division scoping ==============================
def test_cross_division_access_404s(client) -> None:
    c, _ = client
    h_admin = _admin_h(c)
    div_a = _make_division(c, h_admin)
    div_b = _make_division(c, h_admin)
    case = _make_case(c, h_admin, division_id=div_a["id"])
    doc = c.post(
        f"/api/v1/cases/{case['id']}/documents",
        headers=h_admin,
        json={"label": "Scoped"},
    ).json()

    # Build an Accountant mapped only to div_b.
    role = next(r for r in c.get("/api/v1/roles", headers=h_admin).json() if r["name"] == "Accountant")
    other = c.post(
        "/api/v1/users",
        headers=h_admin,
        json={
            "email": "phys-other@x.com",
            "full_name": "Other Acc",
            "role_id": role["id"],
            "password": "Passw0rd!",
            "division_ids": [div_b["id"]],
        },
    ).json()
    h_other = _login(c, "phys-other@x.com")

    listed = c.get(f"/api/v1/cases/{case['id']}/documents", headers=h_other)
    assert listed.status_code == 404
    detail = c.get(f"/api/v1/documents/{doc['id']}", headers=h_other)
    assert detail.status_code == 404


# ============================== Permission gate ==============================
def test_transfer_requires_transfer_permission(client) -> None:
    c, _ = client
    h_admin = _admin_h(c)
    div = _make_division(c, h_admin)
    case = _make_case(c, h_admin, division_id=div["id"])
    doc = c.post(
        f"/api/v1/cases/{case['id']}/documents",
        headers=h_admin,
        json={"label": "Locked"},
    ).json()

    # Sales Manager has documents:read but NOT documents:transfer.
    # Map them to the case's division so the scope check passes and
    # we're actually exercising the permission gate, not data scope.
    role = next(r for r in c.get("/api/v1/roles", headers=h_admin).json() if r["name"] == "Sales Manager")
    sm = c.post(
        "/api/v1/users",
        headers=h_admin,
        json={
            "email": "phys-sm@x.com",
            "full_name": "Phys SM",
            "role_id": role["id"],
            "password": "Passw0rd!",
            "division_ids": [div["id"]],
        },
    ).json()
    h_sm = _login(c, "phys-sm@x.com")

    # Read is fine (read-only).
    listed = c.get(f"/api/v1/cases/{case['id']}/documents", headers=h_sm)
    assert listed.status_code == 200

    # Transfer is blocked.
    r = c.post(
        f"/api/v1/documents/{doc['id']}/transfer",
        headers=h_sm,
        json={"to_user_id": sm["id"]},
    )
    assert r.status_code == 403


# ============================== Print appendix ==============================
def test_print_view_includes_physical_files_section(client) -> None:
    c, _ = client
    h = _admin_h(c)
    div = _make_division(c, h)
    case = _make_case(c, h, division_id=div["id"])
    c.post(
        f"/api/v1/cases/{case['id']}/documents",
        headers=h,
        json={"label": "Original Court Filing", "kind": "court_filing"},
    )

    # Pump through to submit so the print view doesn't blow up on
    # missing required cheques etc. Phase 40 helper attaches a
    # signatory so the submit gate passes.
    attach_default_signatory(c, h, case)

    # Render the HTML print page.
    from app.services import render
    from app.db import session as session_mod

    with session_mod.SessionLocal() as db:
        from app.models.case import Case
        full = db.get(Case, case["id"])
        html = render.render_case_print(db, full)

    assert "Physical Files" in html
    assert "Original Court Filing" in html


# ============================== Signature upload ==============================
def test_transfer_signature_upload_and_view(client) -> None:
    c, _ = client
    h = _admin_h(c)
    div = _make_division(c, h)
    case = _make_case(c, h, division_id=div["id"])
    doc = c.post(
        f"/api/v1/cases/{case['id']}/documents",
        headers=h,
        json={"label": "Signed-for doc"},
    ).json()
    accountant = _make_user_with_role(
        c, h, role_name="Accountant", email="phys-sig-acc@x.com"
    )
    transfer = c.post(
        f"/api/v1/documents/{doc['id']}/transfer",
        headers=h,
        json={"to_user_id": accountant["id"], "note": "Please sign"},
    ).json()
    log_id = transfer["custody_log"][0]["id"]

    up = c.post(
        f"/api/v1/documents/transfers/{log_id}/signature",
        headers=h,
        files={"file": ("sig.png", b"\x89PNG\r\n\x1a\nstub", "image/png")},
    )
    assert up.status_code == 200, up.text
    assert up.json()["signature_filename"] == "sig.png"
    assert up.json()["signature_size"] == 12

    view = c.get(
        f"/api/v1/documents/transfers/{log_id}/signature", headers=h
    )
    assert view.status_code == 200
    assert "inline" in view.headers["content-disposition"]
