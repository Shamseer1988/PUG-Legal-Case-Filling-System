"""Phase 30: case-view tracking, signed JSON export, hash-chain verify."""

import base64
import json

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import *  # noqa: F401,F403
from app.models.case_view import CaseView
from app.models.user import Role, User, UserDivisionMap
from app.services import audit_export, case_views
from app.services.seed import DEFAULT_ADMIN_EMAIL, DEFAULT_ADMIN_PASSWORD, run_seed


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "p30.db"
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


def _login(c: TestClient, email: str) -> dict[str, str]:
    r = c.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Pass@1234"},
    )
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _make_case(c: TestClient, h: dict[str, str]) -> int:
    divs = c.get("/api/v1/masters/divisions", headers=h).json()
    div_id = divs[0]["id"]
    banks = c.get("/api/v1/masters/banks", headers=h).json()
    cust = c.post(
        "/api/v1/masters/customers",
        headers=h,
        json={"code": "CT30", "name": "Acme30", "division_id": div_id},
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
                    "cheque_number": "CH-30-1",
                    "bank_id": banks[0]["id"],
                    "amount": "100.00",
                    "cheque_date": "2026-05-15",
                    "cheque_type": "Normal",
                    "bounce_reason": "Funds",
                },
            ],
        },
    ).json()["id"]
    return case_id


# ---------- case views ----------
def test_case_get_records_a_view(client) -> None:
    c, SessionLocal = client
    h = _admin_h(c)
    case_id = _make_case(c, h)
    # Read case -> triggers record_view
    c.get(f"/api/v1/cases/{case_id}", headers=h)

    db = SessionLocal()
    try:
        n = db.query(CaseView).filter(CaseView.case_id == case_id).count()
        assert n == 1
    finally:
        db.close()


def test_rapid_repeat_views_coalesce(client) -> None:
    """Within COALESCE_SECONDS a re-fetch should NOT add a row."""
    c, SessionLocal = client
    h = _admin_h(c)
    case_id = _make_case(c, h)
    for _ in range(3):
        c.get(f"/api/v1/cases/{case_id}", headers=h)
    db = SessionLocal()
    try:
        n = db.query(CaseView).filter(CaseView.case_id == case_id).count()
        assert n == 1
    finally:
        db.close()


def test_views_endpoint_lists_user_email_and_dedup(client) -> None:
    c, SessionLocal = client
    admin_h = _admin_h(c)
    div_id = c.get("/api/v1/masters/divisions", headers=admin_h).json()[0]["id"]
    other_id = _make_user(SessionLocal, "viewer@pug.local", "Sales Manager", division_id=div_id)
    other_h = _login(c, "viewer@pug.local")
    case_id = _make_case(c, admin_h)

    # Both users open the case
    c.get(f"/api/v1/cases/{case_id}", headers=admin_h)
    c.get(f"/api/v1/cases/{case_id}", headers=other_h)

    r = c.get(f"/api/v1/audit-log/case-views/{case_id}", headers=admin_h)
    assert r.status_code == 200, r.text
    rows = r.json()
    assert len(rows) >= 2
    emails = {r["user_email"] for r in rows}
    assert "viewer@pug.local" in emails
    assert any(r["user_id"] == other_id for r in rows)


def test_views_endpoint_requires_admin_audit_log(client) -> None:
    c, SessionLocal = client
    _make_user(SessionLocal, "salesman@pug.local", "Sales Manager")
    sm_h = _login(c, "salesman@pug.local")
    r = c.get("/api/v1/audit-log/case-views/1", headers=sm_h)
    assert r.status_code == 403


# ---------- signed exports ----------
def test_signing_key_endpoint_returns_pem(client) -> None:
    c, _ = client
    h = _admin_h(c)
    r = c.get("/api/v1/audit-log/signing-key", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["format"] == audit_export.FORMAT_ID
    pub_pem = base64.b64decode(body["public_key"])
    pub = serialization.load_pem_public_key(pub_pem)
    assert isinstance(pub, Ed25519PublicKey)


def test_signed_export_round_trip_verify(client) -> None:
    """Download a signed export and confirm the included signature
    actually validates against the included public key."""
    c, _ = client
    h = _admin_h(c)
    _make_case(c, h)  # trigger some audit rows
    r = c.get("/api/v1/audit-log.signed.json", headers=h)
    assert r.status_code == 200
    bundle = r.json()
    assert bundle["format"] == audit_export.FORMAT_ID
    assert "rows" in bundle and len(bundle["rows"]) > 0
    assert "signature" in bundle and "public_key" in bundle

    assert audit_export.verify_signed_export(bundle) is True


def test_signed_export_tamper_fails_verify(client) -> None:
    """Mutate a single field in the bundle and confirm verification
    flips to False - this is the whole point of the signed export."""
    c, _ = client
    h = _admin_h(c)
    _make_case(c, h)
    r = c.get("/api/v1/audit-log.signed.json", headers=h)
    bundle = r.json()
    assert audit_export.verify_signed_export(bundle) is True

    # Tamper: change the summary of the first row
    if bundle["rows"]:
        bundle["rows"][0]["summary"] = bundle["rows"][0]["summary"] + " [tampered]"
    assert audit_export.verify_signed_export(bundle) is False


def test_signed_export_requires_admin(client) -> None:
    c, _ = client
    assert c.get("/api/v1/audit-log.signed.json").status_code == 401


def test_keypair_reuse_across_calls(client) -> None:
    """Same public key on two separate /signing-key calls - the
    keypair must be generated ONCE and persisted."""
    c, _ = client
    h = _admin_h(c)
    pk1 = c.get("/api/v1/audit-log/signing-key", headers=h).json()["public_key"]
    pk2 = c.get("/api/v1/audit-log/signing-key", headers=h).json()["public_key"]
    assert pk1 == pk2


# ---------- chain verify ----------
def test_verify_chain_passes_on_clean_log(client) -> None:
    c, _ = client
    h = _admin_h(c)
    _make_case(c, h)  # produces audit rows
    r = c.get("/api/v1/audit-log/verify", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["verified"] is True
    assert body["count"] >= 1
    assert body["issues"] == []
