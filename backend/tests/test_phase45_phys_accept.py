"""Phase 45: two-phase physical file transfer acceptance flow."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import *  # noqa: F401,F403
from app.models.user import Role, User
from app.services.seed import DEFAULT_ADMIN_EMAIL, DEFAULT_ADMIN_PASSWORD, run_seed


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "phase45.db"
    storage_dir = tmp_path / "storage"
    storage_dir.mkdir()
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("STORAGE_LOCAL_PATH", str(storage_dir))
    monkeypatch.delenv("SMTP_HOST", raising=False)

    from app.core import config as config_mod
    monkeypatch.setattr(config_mod.settings, "storage_local_path", str(storage_dir))

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


def _login(c: TestClient, email: str, password: str = "Pass@1234") -> str:
    r = c.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


_SEQ = [0]


def _seq() -> int:
    _SEQ[0] += 1
    return _SEQ[0]


def _setup(c: TestClient, SessionLocal):
    """Create two super users, a division, a customer, a case, and a doc."""
    admin_tok = _login(c, DEFAULT_ADMIN_EMAIL, DEFAULT_ADMIN_PASSWORD)
    h = {"Authorization": f"Bearer {admin_tok}"}

    n = _seq()
    div = c.post(
        "/api/v1/masters/divisions",
        headers=h,
        json={"code": f"D45{n}", "name": f"Div45-{n}", "is_active": True},
    )
    assert div.status_code == 201, div.text
    div_id = div.json()["id"]

    cust = c.post(
        "/api/v1/masters/customers",
        headers=h,
        json={"code": f"C45{n}", "name": f"Cust45-{n}", "division_id": div_id, "is_active": True},
    )
    assert cust.status_code == 201, cust.text
    cust_id = cust.json()["id"]

    # Create case via API (admin)
    case = c.post(
        "/api/v1/cases",
        headers=h,
        json={
            "customer_id": cust_id,
            "division_id": div_id,
            "customer_type": "Retail",
            "actual_due_amount": "100",
            "legal_filing_amount": "100",
        },
    )
    assert case.status_code == 201, case.text
    case_id = case.json()["id"]

    # The auto-created Case Folder doc
    docs = c.get(f"/api/v1/cases/{case_id}/documents", headers=h)
    assert docs.status_code == 200
    doc_id = docs.json()[0]["id"] if docs.json() else None

    # If no auto-doc, register one
    if doc_id is None:
        rd = c.post(
            f"/api/v1/cases/{case_id}/documents",
            headers=h,
            json={"label": "Test File", "kind": "other"},
        )
        assert rd.status_code == 201
        doc_id = rd.json()["id"]

    # Create two super users (super so division scoping is bypassed in API calls)
    db = SessionLocal()
    try:
        role = db.query(Role).filter(Role.name == "Accountant").first()
        sender = User(
            email=f"sender45_{n}@pug.local",
            password_hash=hash_password("Pass@1234"),
            full_name=f"Sender {n}",
            role_id=role.id,
            is_active=True,
            is_super=True,
        )
        receiver = User(
            email=f"receiver45_{n}@pug.local",
            password_hash=hash_password("Pass@1234"),
            full_name=f"Receiver {n}",
            role_id=role.id,
            is_active=True,
            is_super=True,
        )
        db.add_all([sender, receiver])
        db.commit()
        return case_id, doc_id, sender.id, receiver.id, f"sender45_{n}@pug.local", f"receiver45_{n}@pug.local"
    finally:
        db.close()


# ---- transfer creates pending ----

def test_transfer_to_user_creates_pending(client):
    c, SL = client
    case_id, doc_id, sender_id, receiver_id, sender_email, receiver_email = _setup(c, SL)
    sender_tok = _login(c, sender_email)

    r = c.post(
        f"/api/v1/documents/{doc_id}/transfer",
        json={"to_user_id": receiver_id, "note": "Please review"},
        headers={"Authorization": f"Bearer {sender_tok}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    # Custody must NOT have moved yet — still with whoever had it before
    assert data["current_holder_user_id"] != receiver_id
    assert data["pending_transfer_log_id"] is not None
    assert data["pending_transfer_to_user_id"] == receiver_id
    assert data["pending_transfer_to_name"] != ""


def test_transfer_to_location_is_immediate(client):
    c, SL = client
    case_id, doc_id, sender_id, receiver_id, sender_email, receiver_email = _setup(c, SL)

    admin_tok = _login(c, DEFAULT_ADMIN_EMAIL, DEFAULT_ADMIN_PASSWORD)
    lr = c.post(
        "/api/v1/masters/document-locations",
        json={"code": "LOC45A", "name": "Cabinet 45", "is_storage": True, "is_active": True},
        headers={"Authorization": f"Bearer {admin_tok}"},
    )
    assert lr.status_code == 201, lr.text
    loc_id = lr.json()["id"]

    sender_tok = _login(c, sender_email)
    r = c.post(
        f"/api/v1/documents/{doc_id}/transfer",
        json={"to_location_id": loc_id, "note": "Archiving"},
        headers={"Authorization": f"Bearer {sender_tok}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    # Location-only transfer → immediate, no pending
    assert data["current_location_id"] == loc_id
    assert data["pending_transfer_log_id"] is None


def test_second_transfer_blocked_while_pending(client):
    c, SL = client
    case_id, doc_id, sender_id, receiver_id, sender_email, receiver_email = _setup(c, SL)
    sender_tok = _login(c, sender_email)

    c.post(
        f"/api/v1/documents/{doc_id}/transfer",
        json={"to_user_id": receiver_id},
        headers={"Authorization": f"Bearer {sender_tok}"},
    )
    r2 = c.post(
        f"/api/v1/documents/{doc_id}/transfer",
        json={"to_user_id": receiver_id},
        headers={"Authorization": f"Bearer {sender_tok}"},
    )
    assert r2.status_code == 409, r2.text


# ---- accept ----

def _initiate_transfer(c, doc_id, receiver_id, sender_tok):
    r = c.post(
        f"/api/v1/documents/{doc_id}/transfer",
        json={"to_user_id": receiver_id},
        headers={"Authorization": f"Bearer {sender_tok}"},
    )
    assert r.status_code == 200, r.text
    return r.json()["pending_transfer_log_id"]


def test_receiver_can_accept(client):
    c, SL = client
    case_id, doc_id, sender_id, receiver_id, sender_email, receiver_email = _setup(c, SL)
    sender_tok = _login(c, sender_email)
    receiver_tok = _login(c, receiver_email)

    log_id = _initiate_transfer(c, doc_id, receiver_id, sender_tok)
    r = c.post(
        f"/api/v1/documents/transfers/{log_id}/accept",
        json={"note": "Received in good condition"},
        headers={"Authorization": f"Bearer {receiver_tok}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    # Custody must have moved to receiver
    assert data["current_holder_user_id"] == receiver_id
    assert data["pending_transfer_log_id"] is None


def test_sender_cannot_accept_own_transfer(client):
    c, SL = client
    case_id, doc_id, sender_id, receiver_id, sender_email, receiver_email = _setup(c, SL)
    sender_tok = _login(c, sender_email)

    log_id = _initiate_transfer(c, doc_id, receiver_id, sender_tok)
    r = c.post(
        f"/api/v1/documents/transfers/{log_id}/accept",
        json={},
        headers={"Authorization": f"Bearer {sender_tok}"},
    )
    assert r.status_code == 403, r.text


def test_accept_updates_custody_log_status(client):
    c, SL = client
    case_id, doc_id, sender_id, receiver_id, sender_email, receiver_email = _setup(c, SL)
    sender_tok = _login(c, sender_email)
    receiver_tok = _login(c, receiver_email)

    log_id = _initiate_transfer(c, doc_id, receiver_id, sender_tok)
    c.post(
        f"/api/v1/documents/transfers/{log_id}/accept",
        json={},
        headers={"Authorization": f"Bearer {receiver_tok}"},
    )
    # Check detail — the log entry must show 'accepted' and have accepted_at set
    detail = c.get(
        f"/api/v1/documents/{doc_id}",
        headers={"Authorization": f"Bearer {receiver_tok}"},
    )
    assert detail.status_code == 200
    log_entries = detail.json()["custody_log"]
    accepted_entry = next(e for e in log_entries if e["id"] == log_id)
    assert accepted_entry["transfer_status"] == "accepted"
    assert accepted_entry["accepted_at"] is not None


# ---- reject ----

def test_receiver_can_reject(client):
    c, SL = client
    case_id, doc_id, sender_id, receiver_id, sender_email, receiver_email = _setup(c, SL)
    sender_tok = _login(c, sender_email)
    receiver_tok = _login(c, receiver_email)

    log_id = _initiate_transfer(c, doc_id, receiver_id, sender_tok)
    r = c.post(
        f"/api/v1/documents/transfers/{log_id}/reject",
        json={"note": "Wrong file"},
        headers={"Authorization": f"Bearer {receiver_tok}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["transfer_status"] == "rejected"


def test_sender_can_retry_after_rejection(client):
    c, SL = client
    case_id, doc_id, sender_id, receiver_id, sender_email, receiver_email = _setup(c, SL)
    sender_tok = _login(c, sender_email)
    receiver_tok = _login(c, receiver_email)

    log_id = _initiate_transfer(c, doc_id, receiver_id, sender_tok)
    c.post(
        f"/api/v1/documents/transfers/{log_id}/reject",
        json={"note": "Wrong file"},
        headers={"Authorization": f"Bearer {receiver_tok}"},
    )
    # Should be able to transfer again
    r2 = c.post(
        f"/api/v1/documents/{doc_id}/transfer",
        json={"to_user_id": receiver_id},
        headers={"Authorization": f"Bearer {sender_tok}"},
    )
    assert r2.status_code == 200, r2.text


def test_third_party_cannot_reject(client):
    c, SL = client
    case_id, doc_id, sender_id, receiver_id, sender_email, receiver_email = _setup(c, SL)
    sender_tok = _login(c, sender_email)
    admin_tok = _login(c, DEFAULT_ADMIN_EMAIL, DEFAULT_ADMIN_PASSWORD)

    log_id = _initiate_transfer(c, doc_id, receiver_id, sender_tok)
    # Admin is not the `to_user_id` — should get 403
    r = c.post(
        f"/api/v1/documents/transfers/{log_id}/reject",
        json={},
        headers={"Authorization": f"Bearer {admin_tok}"},
    )
    assert r.status_code == 403, r.text


# ---- pending-incoming report ----

def test_pending_incoming_report(client):
    c, SL = client
    case_id, doc_id, sender_id, receiver_id, sender_email, receiver_email = _setup(c, SL)
    sender_tok = _login(c, sender_email)
    receiver_tok = _login(c, receiver_email)

    _initiate_transfer(c, doc_id, receiver_id, sender_tok)

    r = c.get(
        "/api/v1/documents/reports/pending-incoming",
        headers={"Authorization": f"Bearer {receiver_tok}"},
    )
    assert r.status_code == 200, r.text
    rows = r.json()
    assert len(rows) >= 1
    row = next(x for x in rows if x["document_id"] == doc_id)
    assert row["transfer_status"] == "pending"
    assert row["case_id"] == case_id


def test_pending_incoming_empty_after_accept(client):
    c, SL = client
    case_id, doc_id, sender_id, receiver_id, sender_email, receiver_email = _setup(c, SL)
    sender_tok = _login(c, sender_email)
    receiver_tok = _login(c, receiver_email)

    log_id = _initiate_transfer(c, doc_id, receiver_id, sender_tok)
    c.post(
        f"/api/v1/documents/transfers/{log_id}/accept",
        json={},
        headers={"Authorization": f"Bearer {receiver_tok}"},
    )

    r = c.get(
        "/api/v1/documents/reports/pending-incoming",
        headers={"Authorization": f"Bearer {receiver_tok}"},
    )
    assert r.status_code == 200
    matching = [x for x in r.json() if x["document_id"] == doc_id]
    assert matching == []


# ---- doc detail shows pending info ----

def test_doc_list_shows_pending_fields(client):
    c, SL = client
    case_id, doc_id, sender_id, receiver_id, sender_email, receiver_email = _setup(c, SL)
    sender_tok = _login(c, sender_email)

    log_id = _initiate_transfer(c, doc_id, receiver_id, sender_tok)

    docs = c.get(
        f"/api/v1/cases/{case_id}/documents",
        headers={"Authorization": f"Bearer {sender_tok}"},
    )
    assert docs.status_code == 200
    doc_row = next(d for d in docs.json() if d["id"] == doc_id)
    assert doc_row["pending_transfer_log_id"] == log_id
    assert doc_row["pending_transfer_to_user_id"] == receiver_id
