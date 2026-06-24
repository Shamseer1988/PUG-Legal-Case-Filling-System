"""Phase 40: customer partners + joint cheque signatories on cases."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import *  # noqa: F401,F403
from app.services.seed import DEFAULT_ADMIN_EMAIL, DEFAULT_ADMIN_PASSWORD, run_seed


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "p40.db"
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


_P40_SEQ = [0]


def _make_customer(c, h, *, name: str) -> dict:
    _P40_SEQ[0] += 1
    code = f"P40-{_P40_SEQ[0]:03d}"
    div_id = c.get("/api/v1/masters/divisions", headers=h).json()[0]["id"]
    return c.post(
        "/api/v1/masters/customers",
        headers=h,
        json={"code": code, "name": name, "division_id": div_id},
    ).json()


# ============================== Partner CRUD ==============================
def test_partner_crud_round_trip(client) -> None:
    c, _ = client
    h = _admin_h(c)
    cust = _make_customer(c, h, name="Joint Sign Co")

    # Create
    p = c.post(
        f"/api/v1/masters/customers/{cust['id']}/partners",
        headers=h,
        json={
            "name": "Ali Hassan",
            "id_number": "784-1990-1234567-1",
            "id_expiry_date": "2030-01-01",
            "nationality": "UAE",
            "residency_status": "inside_country",
            "is_cheque_signatory": True,
            "is_authorised_signatory": True,
            "is_admin_contact": False,
            "phone": "+971-50-0000000",
            "email": "ali@example.com",
        },
    )
    assert p.status_code == 201, p.text
    body = p.json()
    assert body["name"] == "Ali Hassan"
    assert body["customer_id"] == cust["id"]
    assert body["is_cheque_signatory"] is True
    assert body["residency_status"] == "inside_country"

    # List
    rows = c.get(
        f"/api/v1/masters/customers/{cust['id']}/partners", headers=h
    ).json()
    assert len(rows) == 1 and rows[0]["id"] == body["id"]

    # Update - flip residency, drop one role
    patched = c.patch(
        f"/api/v1/masters/customers/{cust['id']}/partners/{body['id']}",
        headers=h,
        json={
            "residency_status": "outside_country",
            "is_authorised_signatory": False,
        },
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["residency_status"] == "outside_country"
    assert patched.json()["is_authorised_signatory"] is False
    assert patched.json()["is_cheque_signatory"] is True

    # Delete
    rm = c.delete(
        f"/api/v1/masters/customers/{cust['id']}/partners/{body['id']}",
        headers=h,
    )
    assert rm.status_code == 204
    after = c.get(
        f"/api/v1/masters/customers/{cust['id']}/partners", headers=h
    ).json()
    assert after == []


def test_partner_id_document_upload_view_delete(client) -> None:
    c, _ = client
    h = _admin_h(c)
    cust = _make_customer(c, h, name="Doc Co")
    p = c.post(
        f"/api/v1/masters/customers/{cust['id']}/partners",
        headers=h,
        json={"name": "Mariam Khan", "is_cheque_signatory": True},
    ).json()

    # Upload an ID copy
    up = c.post(
        f"/api/v1/masters/customers/{cust['id']}/partners/{p['id']}/id-document",
        headers=h,
        files={"file": ("id.pdf", b"%PDF-ID", "application/pdf")},
    )
    assert up.status_code == 200, up.text
    assert up.json()["id_document_filename"] == "id.pdf"
    assert up.json()["id_document_size"] == 7

    # View (inline)
    view = c.get(
        f"/api/v1/masters/customers/{cust['id']}/partners/{p['id']}/id-document",
        headers=h,
    )
    assert view.status_code == 200
    assert "inline" in view.headers["content-disposition"]

    # Delete
    rm = c.delete(
        f"/api/v1/masters/customers/{cust['id']}/partners/{p['id']}/id-document",
        headers=h,
    )
    assert rm.status_code == 200, rm.text
    assert rm.json()["id_document_filename"] == ""
    assert rm.json()["id_document_size"] == 0


# ============================== Case integration ==============================
def _make_case_with_partners(c, h, *, signer_ids: list[int] | None = None):
    cust = _make_customer(c, h, name="Case Co")
    # Mint two cheque signatories so we can test joint-sign cases.
    p1 = c.post(
        f"/api/v1/masters/customers/{cust['id']}/partners",
        headers=h,
        json={"name": "Signer One", "is_cheque_signatory": True},
    ).json()
    p2 = c.post(
        f"/api/v1/masters/customers/{cust['id']}/partners",
        headers=h,
        json={"name": "Signer Two", "is_cheque_signatory": True},
    ).json()
    if signer_ids is None:
        signer_ids = [p1["id"], p2["id"]]

    div_id = c.get("/api/v1/masters/divisions", headers=h).json()[0]["id"]
    banks = c.get("/api/v1/masters/banks", headers=h).json()
    body = {
        "customer_id": cust["id"],
        "division_id": div_id,
        "is_civil": True,
        "cheques": [
            {
                "cheque_number": "CH-P40",
                "bank_id": banks[0]["id"],
                "amount": "100",
                "cheque_date": "2026-05-15",
                "cheque_type": "Normal",
                "bounce_reason": "Funds",
            }
        ],
        "cheque_signatory_partner_ids": signer_ids,
    }
    case = c.post("/api/v1/cases", headers=h, json=body).json()
    return case, [p1, p2]


def test_create_case_with_joint_signatories(client) -> None:
    c, _ = client
    h = _admin_h(c)
    case, partners = _make_case_with_partners(c, h)
    assert sorted(case["cheque_signatory_partner_ids"]) == sorted(
        [p["id"] for p in partners]
    )


def test_patch_case_replaces_signatory_set(client) -> None:
    c, _ = client
    h = _admin_h(c)
    case, partners = _make_case_with_partners(c, h)
    case_id = case["id"]
    # Drop one signatory
    patched = c.patch(
        f"/api/v1/cases/{case_id}",
        headers=h,
        json={"cheque_signatory_partner_ids": [partners[0]["id"]]},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["cheque_signatory_partner_ids"] == [partners[0]["id"]]


def test_submit_requires_at_least_one_signatory(client) -> None:
    """Phase 40: empty signatory list at submit-time -> 400."""
    c, _ = client
    h = _admin_h(c)
    case, partners = _make_case_with_partners(c, h, signer_ids=[])
    case_id = case["id"]
    r = c.post(f"/api/v1/cases/{case_id}/submit", headers=h)
    assert r.status_code == 400
    assert "signatory" in r.json()["detail"].lower()

    # Add one and re-submit -> succeeds.
    c.patch(
        f"/api/v1/cases/{case_id}",
        headers=h,
        json={"cheque_signatory_partner_ids": [partners[0]["id"]]},
    )
    ok = c.post(f"/api/v1/cases/{case_id}/submit", headers=h)
    assert ok.status_code == 200, ok.text


def test_partner_must_belong_to_case_customer(client) -> None:
    """Cross-customer leakage: picking a partner from a different
    customer must be rejected."""
    c, _ = client
    h = _admin_h(c)
    case, _ = _make_case_with_partners(c, h)
    # Mint a partner under a different customer.
    other_cust = _make_customer(c, h, name="Other Co")
    foreign = c.post(
        f"/api/v1/masters/customers/{other_cust['id']}/partners",
        headers=h,
        json={"name": "Foreigner", "is_cheque_signatory": True},
    ).json()
    r = c.patch(
        f"/api/v1/cases/{case['id']}",
        headers=h,
        json={"cheque_signatory_partner_ids": [foreign["id"]]},
    )
    assert r.status_code == 400
    assert "customer" in r.json()["detail"].lower()


def test_print_view_shows_signatory_names(client) -> None:
    """The printed HTML preview lists each partner name (and ID#
    when set) under the Customer block."""
    c, _ = client
    h = _admin_h(c)
    case, partners = _make_case_with_partners(c, h)

    # Fill an ID number on one partner so the (ID# ...) span exists.
    c.patch(
        f"/api/v1/masters/customers/{case['customer_id']}/partners/{partners[0]['id']}",
        headers=h,
        json={"id_number": "AB123"},
    )

    # Render the HTML preview through the renderer service directly.
    from app.models.case import Case
    from app.services import render

    from app.db import session as session_mod

    db = session_mod.SessionLocal()
    try:
        c_row = db.get(Case, case["id"])
        html = render.render_case_print(db, c_row)
    finally:
        db.close()

    assert "Cheque Signatories" in html
    assert "Signer One" in html
    assert "Signer Two" in html
    assert "AB123" in html


# ============================== Scoped masters ==============================
def test_partner_routes_scoped_to_user_division(client) -> None:
    """Non-super users without the right division mapping can't
    see another customer's partners."""
    c, SessionLocal = client
    admin_h = _admin_h(c)

    div_a = c.post(
        "/api/v1/masters/divisions",
        headers=admin_h,
        json={"code": "P40DA", "name": "Alpha"},
    ).json()
    div_b = c.post(
        "/api/v1/masters/divisions",
        headers=admin_h,
        json={"code": "P40DB", "name": "Beta"},
    ).json()
    cust_b = c.post(
        "/api/v1/masters/customers",
        headers=admin_h,
        json={"code": "P40CB", "name": "Beta Cust", "division_id": div_b["id"]},
    ).json()
    c.post(
        f"/api/v1/masters/customers/{cust_b['id']}/partners",
        headers=admin_h,
        json={"name": "Beta Signer", "is_cheque_signatory": True},
    )

    # Create an Accountant mapped to Alpha only.
    roles = c.get("/api/v1/roles", headers=admin_h).json()
    role_id = next(r["id"] for r in roles if r["name"] == "Accountant")
    c.post(
        "/api/v1/users",
        headers=admin_h,
        json={
            "email": "alphaonly@x.com",
            "full_name": "AlphaOnly",
            "password": "Pa55word!",
            "role_id": role_id,
            "is_active": True,
            "is_super": False,
            "is_all_divisions": False,
            "division_ids": [div_a["id"]],
        },
    )
    tok = c.post(
        "/api/v1/auth/login",
        json={"email": "alphaonly@x.com", "password": "Pa55word!"},
    ).json()["access_token"]
    acc_h = {"Authorization": f"Bearer {tok}"}

    r = c.get(
        f"/api/v1/masters/customers/{cust_b['id']}/partners", headers=acc_h
    )
    assert r.status_code == 404
