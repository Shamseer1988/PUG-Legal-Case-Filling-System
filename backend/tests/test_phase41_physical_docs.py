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
    banks = c.get("/api/v1/masters/banks", headers=h).json()
    case = c.post(
        "/api/v1/cases",
        headers=h,
        json={
            "customer_id": cust["id"],
            "division_id": division_id,
            "customer_type": "Retail",
            "actual_due_amount": "100",
            "legal_filing_amount": "100",
            # Submit needs at least one cheque with a number.
            "cheques": [
                {
                    "cheque_number": f"CHQ-{_P41_SEQ[0]}",
                    "bank_id": banks[0]["id"] if banks else None,
                    "amount": "100",
                    "cheque_type": "Normal",
                }
            ],
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

    # Hand off to a lawyer-type user (Phase 45: requires their acceptance).
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
    # Phase 45: custody does NOT move until lawyer accepts.
    assert after["current_holder_user_id"] != lawyer["id"]
    assert after["pending_transfer_to_user_id"] == lawyer["id"]
    pending_log_id = after["pending_transfer_log_id"]
    assert pending_log_id is not None
    # The new log entry is already in the log (status=pending).
    assert len(after["custody_log"]) == 2
    newest = after["custody_log"][0]
    assert newest["to_user_id"] == lawyer["id"]
    assert newest["note"] == "Filing tomorrow at court"
    assert newest["transfer_status"] == "pending"

    # Lawyer accepts → custody moves.
    lawyer_h = _login(c, "phys-lawyer@x.com")
    accepted = c.post(
        f"/api/v1/documents/transfers/{pending_log_id}/accept",
        headers=lawyer_h,
        json={},
    )
    assert accepted.status_code == 200, accepted.text
    final = accepted.json()
    assert final["current_holder_user_id"] == lawyer["id"]
    assert final["current_holder_name"] == lawyer["full_name"]
    assert final["current_location_id"] is None
    assert final["pending_transfer_log_id"] is None


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
    d2 = c.post(  # noqa: F841
        f"/api/v1/cases/{case['id']}/documents",
        headers=h_admin,
        json={"label": "Doc-B"},
    ).json()
    transfer = c.post(
        f"/api/v1/documents/{d1['id']}/transfer",
        headers=h_admin,
        json={"to_user_id": accountant["id"]},
    ).json()
    # Phase 45: accountant must accept before the doc shows as "with-me".
    log_id = transfer["pending_transfer_log_id"]
    assert log_id is not None
    acc_r = c.post(
        f"/api/v1/documents/transfers/{log_id}/accept",
        headers=h_acc,
        json={},
    )
    assert acc_r.status_code == 200, acc_r.text

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
    transfer_r = c.post(
        f"/api/v1/documents/{held['id']}/transfer",
        headers=h,
        json={"to_user_id": accountant["id"]},
    ).json()
    # Phase 45: accountant must accept before the doc appears in the overdue report.
    h_acc = _login(c, "phys-acc2@x.com")
    acc_r = c.post(
        f"/api/v1/documents/transfers/{transfer_r['pending_transfer_log_id']}/accept",
        headers=h_acc,
        json={},
    )
    assert acc_r.status_code == 200, acc_r.text

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

    # Build a custom role with read-only access — no documents:transfer.
    # (System roles in the approval chain now all carry transfer perms
    # because Case Folder hops up the chain in person; we need a fresh
    # role to exercise the permission gate.)
    role = c.post(
        "/api/v1/roles",
        headers=h_admin,
        json={
            "name": "Read Only Tester",
            "permissions": ["cases:read", "documents:read"],
        },
    ).json()
    ro = c.post(
        "/api/v1/users",
        headers=h_admin,
        json={
            "email": "phys-ro@x.com",
            "full_name": "Phys RO",
            "role_id": role["id"],
            "password": "Passw0rd!",
            "division_ids": [div["id"]],
        },
    ).json()
    h_ro = _login(c, "phys-ro@x.com")

    # Read is fine (read-only).
    listed = c.get(f"/api/v1/cases/{case['id']}/documents", headers=h_ro)
    assert listed.status_code == 200

    # Transfer is blocked.
    r = c.post(
        f"/api/v1/documents/{doc['id']}/transfer",
        headers=h_ro,
        json={"to_user_id": ro["id"]},
    )
    assert r.status_code == 403


# ============================== Print appendix ==============================
def test_print_view_omits_physical_files_section(client) -> None:
    """Physical Files chain-of-custody is internal-only and must
    not leak into the case application form's print/PDF output."""
    c, _ = client
    h = _admin_h(c)
    div = _make_division(c, h)
    case = _make_case(c, h, division_id=div["id"])
    c.post(
        f"/api/v1/cases/{case['id']}/documents",
        headers=h,
        json={"label": "Original Court Filing", "kind": "court_filing"},
    )

    attach_default_signatory(c, h, case)

    from app.services import render
    from app.db import session as session_mod

    with session_mod.SessionLocal() as db:
        from app.models.case import Case
        full = db.get(Case, case["id"])
        html = render.render_case_print(db, full)

    assert "Physical Files" not in html
    assert "Original Court Filing" not in html


# ============================== Signature upload ==============================
# ============================== Phase 41B: auto-create + workflow gates ==============================
def test_create_case_auto_registers_case_folder(client) -> None:
    """Every new case should arrive with a "Case Folder" physical
    document pre-registered so the chain-of-custody log starts on
    day 1 instead of waiting for the operator to remember."""
    c, _ = client
    h = _admin_h(c)
    div = _make_division(c, h)
    case = _make_case(c, h, division_id=div["id"])

    docs = c.get(f"/api/v1/cases/{case['id']}/documents", headers=h).json()
    assert len(docs) == 1, docs
    folder = docs[0]
    assert folder["kind"] == "case_folder"
    assert folder["label"] == "Case Folder"

    # The auto-created head log entry uses the creator as "recorded by"
    # with no holder yet (it hasn't moved off the Accountant's desk).
    detail = c.get(f"/api/v1/documents/{folder['id']}", headers=h).json()
    assert len(detail["custody_log"]) == 1
    head = detail["custody_log"][0]
    assert head["from_user_id"] is None
    assert head["to_user_id"] is None
    assert head["note"] == "Case opened"


def _make_lawyer(c, h, *, email: str, division_id: int | None = None) -> dict:
    role = next(
        r for r in c.get("/api/v1/roles", headers=h).json() if r["name"] == "Lawyer"
    )
    return c.post(
        "/api/v1/users",
        headers=h,
        json={
            "email": email,
            "full_name": email.split("@")[0],
            "role_id": role["id"],
            "password": "Passw0rd!",
            "division_ids": [division_id] if division_id else [],
        },
    ).json()


def _approve_case_to_chairman(c, h, case_id: int) -> None:
    """Push a draft case through the full approval chain to Approved.

    Each stage is approved via the generic transitions endpoint so
    we don't have to know each role's specific approval URL.
    """
    attach_default_signatory(c, h, case_id)
    c.post(f"/api/v1/cases/{case_id}/submit", headers=h)
    for _ in range(6):
        case = c.get(f"/api/v1/cases/{case_id}", headers=h).json()
        if case["status"] == "Approved":
            return
        c.post(
            f"/api/v1/cases/{case_id}/transition",
            headers=h,
            json={"action": "approve", "comment": "ok"},
        )
    case = c.get(f"/api/v1/cases/{case_id}", headers=h).json()
    assert case["status"] == "Approved", case


def test_filing_blocked_until_folder_handed_to_lawyer(client) -> None:
    c, _ = client
    h = _admin_h(c)
    div = _make_division(c, h)
    case = _make_case(c, h, division_id=div["id"])
    # Make sure a Lawyer-role user exists so the gate activates;
    # without one, the gate is a no-op for backward compat.
    lawyer = _make_lawyer(c, h, email="phys-lawyer-gate@x.com")

    # Engage the gate by recording one transfer (to a storage
    # location, *not* the lawyer). Without an explicit movement the
    # gate is a no-op for backward compatibility - it only fires
    # once the operator is actively using the chain of custody.
    docs = c.get(f"/api/v1/cases/{case['id']}/documents", headers=h).json()
    folder = docs[0]
    storage_loc = c.post(
        "/api/v1/masters/document-locations",
        headers=h,
        json={"code": _next_code("LOC"), "name": "Accountant Cabinet", "is_storage": True},
    ).json()
    c.post(
        f"/api/v1/documents/{folder['id']}/transfer",
        headers=h,
        json={"to_location_id": storage_loc["id"], "note": "Parking"},
    )

    _approve_case_to_chairman(c, h, case["id"])

    # File attempt #1: folder is sitting in a cabinet, not with the
    # lawyer. Backend MUST refuse.
    r1 = c.post(
        f"/api/v1/cases/{case['id']}/court-filing",
        headers=h,
        json={"police_case_no": "P1", "court_case_no": "C1"},
    )
    assert r1.status_code == 400, r1.text
    assert "physical case folder" in r1.json()["detail"].lower()

    # Hand the folder to the lawyer, then retry - should succeed.
    transfer2 = c.post(
        f"/api/v1/documents/{folder['id']}/transfer",
        headers=h,
        json={"to_user_id": lawyer["id"], "note": "For court filing"},
    ).json()
    # Phase 45: lawyer must accept before custody moves (and gate passes).
    lawyer_h = _login(c, "phys-lawyer-gate@x.com")
    acc2 = c.post(
        f"/api/v1/documents/transfers/{transfer2['pending_transfer_log_id']}/accept",
        headers=lawyer_h,
        json={},
    )
    assert acc2.status_code == 200, acc2.text
    r2 = c.post(
        f"/api/v1/cases/{case['id']}/court-filing",
        headers=h,
        json={"police_case_no": "P1", "court_case_no": "C1"},
    )
    assert r2.status_code == 201, r2.text


def test_closing_blocked_until_folder_back_in_storage(client) -> None:
    c, _ = client
    h = _admin_h(c)
    div = _make_division(c, h)
    case = _make_case(c, h, division_id=div["id"])
    lawyer = _make_lawyer(c, h, email="phys-lawyer-close@x.com")
    storage_loc = c.post(
        "/api/v1/masters/document-locations",
        headers=h,
        json={"code": _next_code("LOC"), "name": "Archive", "is_storage": True},
    ).json()
    transient_loc = c.post(
        "/api/v1/masters/document-locations",
        headers=h,
        json={
            "code": _next_code("LOC"),
            "name": "Lawyer Office",
            "is_storage": False,
        },
    ).json()

    _approve_case_to_chairman(c, h, case["id"])
    docs = c.get(f"/api/v1/cases/{case['id']}/documents", headers=h).json()
    folder = docs[0]
    # Hand to the lawyer + park at a non-storage location so we can
    # actually reach Closed-attempt land.
    transfer_close = c.post(
        f"/api/v1/documents/{folder['id']}/transfer",
        headers=h,
        json={
            "to_user_id": lawyer["id"],
            "to_location_id": transient_loc["id"],
        },
    ).json()
    # Phase 45: lawyer accepts so custody moves (filing gate requires lawyer custody).
    lawyer_h_close = _login(c, "phys-lawyer-close@x.com")
    acc_close = c.post(
        f"/api/v1/documents/transfers/{transfer_close['pending_transfer_log_id']}/accept",
        headers=lawyer_h_close,
        json={},
    )
    assert acc_close.status_code == 200, acc_close.text
    c.post(
        f"/api/v1/cases/{case['id']}/court-filing",
        headers=h,
        json={"police_case_no": "P", "court_case_no": "C"},
    )

    # Try to close while the folder is at a non-storage location.
    bad = c.post(
        f"/api/v1/cases/{case['id']}/close",
        headers=h,
        json={
            "closure_type": "settlement",
            "settlement_agreement_ref": "SET-1",
            "command": "Settled",
        },
    )
    assert bad.status_code == 400, bad.text
    assert "storage" in bad.json()["detail"].lower()

    # Return the folder to a storage location, then close - allowed.
    c.post(
        f"/api/v1/documents/{folder['id']}/transfer",
        headers=h,
        json={"to_location_id": storage_loc["id"], "note": "Filed away"},
    )
    ok = c.post(
        f"/api/v1/cases/{case['id']}/close",
        headers=h,
        json={
            "closure_type": "settlement",
            "settlement_agreement_ref": "SET-1",
            "command": "Settled",
        },
    )
    assert ok.status_code == 201, ok.text


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
