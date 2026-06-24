"""Phase 24: signed case form upload/replace/delete by FM or Lawyer."""

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
from app.models.case import CaseAttachment
from app.models.user import Role, User, UserDivisionMap
from app.services.seed import DEFAULT_ADMIN_EMAIL, DEFAULT_ADMIN_PASSWORD, run_seed


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "p24.db"
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


def _make_case(c: TestClient, h: dict[str, str]) -> int:
    divs = c.get("/api/v1/masters/divisions", headers=h).json()
    div_id = divs[0]["id"]
    banks = c.get("/api/v1/masters/banks", headers=h).json()
    cust = c.post(
        "/api/v1/masters/customers",
        headers=h,
        json={"code": "CT24", "name": "Acme24", "division_id": div_id},
    ).json()
    return c.post(
        "/api/v1/cases",
        headers=h,
        json={
            "customer_id": cust["id"],
            "division_id": div_id,
            "is_civil": True,
            "cheques": [
                {
                    "cheque_number": "CH-24-1",
                    "bank_id": banks[0]["id"],
                    "amount": "1000.00",
                    "cheque_date": "2026-05-15",
                    "cheque_type": "Normal",
                    "bounce_reason": "Funds",
                },
            ],
        },
    ).json()["id"]


def _make_role_user(SessionLocal, email: str, role_name: str, division_id: int | None = None) -> int:
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


def test_signed_form_round_trip_admin(client) -> None:
    c, _ = client
    h = _admin_h(c)
    case_id = _make_case(c, h)

    # Nothing yet
    assert c.get(f"/api/v1/cases/{case_id}/signed-form", headers=h).json() is None

    payload = b"%PDF-signed-1"
    r = c.post(
        f"/api/v1/cases/{case_id}/signed-form",
        headers=h,
        files={"file": ("signed.pdf", io.BytesIO(payload), "application/pdf")},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["category"] == "Signed Case Form"
    assert body["size_bytes"] == len(payload)
    att_id = body["id"]

    # GET returns the metadata
    got = c.get(f"/api/v1/cases/{case_id}/signed-form", headers=h).json()
    assert got["id"] == att_id

    # Downloadable via the existing attachment endpoint
    r = c.get(
        f"/api/v1/cases/{case_id}/attachments/{att_id}/download",
        headers=h,
    )
    assert r.status_code == 200
    assert r.content == payload


def test_signed_form_replace_evicts_previous(client) -> None:
    c, _ = client
    h = _admin_h(c)
    case_id = _make_case(c, h)

    first = c.post(
        f"/api/v1/cases/{case_id}/signed-form",
        headers=h,
        files={"file": ("v1.pdf", io.BytesIO(b"v1"), "application/pdf")},
    ).json()
    second = c.post(
        f"/api/v1/cases/{case_id}/signed-form",
        headers=h,
        files={"file": ("v2.pdf", io.BytesIO(b"v2-newer"), "application/pdf")},
    ).json()
    assert first["id"] != second["id"]

    # Old attachment row is gone
    assert (
        c.get(
            f"/api/v1/cases/{case_id}/attachments/{first['id']}/download",
            headers=h,
        ).status_code
        == 404
    )
    # Only one signed-form attachment remains on the case
    got = c.get(f"/api/v1/cases/{case_id}/signed-form", headers=h).json()
    assert got["id"] == second["id"]


def test_signed_form_delete(client) -> None:
    c, _ = client
    h = _admin_h(c)
    case_id = _make_case(c, h)
    c.post(
        f"/api/v1/cases/{case_id}/signed-form",
        headers=h,
        files={"file": ("x.pdf", io.BytesIO(b"x"), "application/pdf")},
    )
    r = c.delete(f"/api/v1/cases/{case_id}/signed-form", headers=h)
    assert r.status_code == 204
    assert c.get(f"/api/v1/cases/{case_id}/signed-form", headers=h).json() is None


def test_signed_form_upload_blocked_for_unprivileged_role(client) -> None:
    """A Sales Manager doesn't hold cases:signed_form and must
    receive a 403 instead of silently shadowing the file."""
    c, SessionLocal = client
    h = _admin_h(c)
    case_id = _make_case(c, h)
    _make_role_user(SessionLocal, "sm-only@pug.local", "Sales Manager")
    sm = _login(c, "sm-only@pug.local")
    r = c.post(
        f"/api/v1/cases/{case_id}/signed-form",
        headers=sm,
        files={"file": ("x.pdf", io.BytesIO(b"x"), "application/pdf")},
    )
    assert r.status_code == 403


def test_signed_form_allowed_for_lawyer_and_fm(client) -> None:
    c, SessionLocal = client
    h = _admin_h(c)
    case_id = _make_case(c, h)
    div_id = c.get(f"/api/v1/cases/{case_id}", headers=h).json()["division_id"]

    _make_role_user(SessionLocal, "fm@pug.local", "Finance Manager", division_id=div_id)
    _make_role_user(SessionLocal, "lawyer@pug.local", "Lawyer", division_id=div_id)

    for email in ("fm@pug.local", "lawyer@pug.local"):
        hh = _login(c, email)
        r = c.post(
            f"/api/v1/cases/{case_id}/signed-form",
            headers=hh,
            files={"file": (f"by-{email}.pdf", io.BytesIO(b"x"), "application/pdf")},
        )
        assert r.status_code == 201, f"{email}: {r.text}"


def test_signed_form_action_in_admin_capabilities(client) -> None:
    c, _ = client
    h = _admin_h(c)
    body = c.get("/api/v1/auth/me/capabilities", headers=h).json()
    assert "case.signed_form.upload" in body["actions"]


def test_signed_form_requires_auth(client) -> None:
    c, _ = client
    assert c.get("/api/v1/cases/1/signed-form").status_code == 401
    assert c.post(
        "/api/v1/cases/1/signed-form",
        files={"file": ("x", io.BytesIO(b""), "application/pdf")},
    ).status_code == 401
    assert c.delete("/api/v1/cases/1/signed-form").status_code == 401
