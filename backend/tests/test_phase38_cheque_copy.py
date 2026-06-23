"""Phase 38: cheque-row paperclip = cheque copy (always OCR),
bank letter moves to case-level attachments, draft cheques can be
saved without a cheque_number."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.attachment_categories import (
    ATTACHMENT_CATEGORIES,
    CATEGORY_BANK_RETURN_LETTER,
)
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import *  # noqa: F401,F403
from app.services.seed import DEFAULT_ADMIN_EMAIL, DEFAULT_ADMIN_PASSWORD, run_seed


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "p38.db"
    storage_dir = tmp_path / "storage"
    storage_dir.mkdir()
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("STORAGE_LOCAL_PATH", str(storage_dir))
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.delenv("OCR_VISION_API_KEY", raising=False)

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


def _h(c: TestClient) -> dict[str, str]:
    r = c.post(
        "/api/v1/auth/login",
        json={"email": DEFAULT_ADMIN_EMAIL, "password": DEFAULT_ADMIN_PASSWORD},
    )
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _make_case_with_blank_cheque(c, h, *, code: str):
    div_id = c.get("/api/v1/masters/divisions", headers=h).json()[0]["id"]
    cust = c.post(
        "/api/v1/masters/customers",
        headers=h,
        json={"code": code, "name": f"P38 cust {code}", "division_id": div_id},
    ).json()
    case = c.post(
        "/api/v1/cases",
        headers=h,
        json={
            "customer_id": cust["id"],
            "division_id": div_id,
            "is_civil": True,
            # Phase 38: cheque_number is allowed to be blank in draft.
            "cheques": [
                {
                    "cheque_number": "",
                    "bank_id": None,
                    "amount": "0",
                    "cheque_date": None,
                    "cheque_type": "Normal",
                    "bounce_reason": "",
                }
            ],
        },
    )
    return case


def test_draft_accepts_cheque_with_empty_number(client) -> None:
    """Phase 38: empty cheque_number is allowed at draft time so
    the user can attach the cheque copy before they've typed the
    number. The cheque row gets a server-side id immediately."""
    c, _ = client
    h = _h(c)
    r = _make_case_with_blank_cheque(c, h, code="P38-0001")
    assert r.status_code == 201, r.text
    body = r.json()
    assert len(body["cheques"]) == 1
    assert body["cheques"][0]["cheque_number"] == ""
    assert body["cheques"][0]["id"] is not None


def test_submit_rejects_cases_with_empty_cheque_number(client) -> None:
    """Phase 38: blank cheque_number is fine during draft but must
    be filled before submission."""
    c, _ = client
    h = _h(c)
    case = _make_case_with_blank_cheque(c, h, code="P38-0002").json()
    r = c.post(f"/api/v1/cases/{case['id']}/submit", headers=h)
    assert r.status_code == 400
    assert "cheque number" in r.json()["detail"].lower()

    # Fill the number and try again.
    cheque = case["cheques"][0]
    patch = c.patch(
        f"/api/v1/cases/{case['id']}",
        headers=h,
        json={
            "cheques": [
                {
                    "cheque_number": "FILLED-1",
                    "bank_id": cheque["bank_id"],
                    "amount": "10",
                    "cheque_date": "2026-05-15",
                    "cheque_type": "Normal",
                    "bounce_reason": "",
                }
            ]
        },
    )
    assert patch.status_code == 200, patch.text
    sub = c.post(f"/api/v1/cases/{case['id']}/submit", headers=h)
    assert sub.status_code == 200, sub.text


def test_cheque_attachment_upload_drops_is_bank_return_form_param(client) -> None:
    """Phase 38: the endpoint no longer accepts is_bank_return_letter
    (it was always a cheque copy in practice). Sending the legacy
    param is harmless - FastAPI just ignores unknown form fields."""
    c, _ = client
    h = _h(c)
    case = _make_case_with_blank_cheque(c, h, code="P38-0003").json()
    cheque_id = case["cheques"][0]["id"]
    r = c.post(
        f"/api/v1/cases/{case['id']}/cheques/{cheque_id}/attachments",
        headers=h,
        files={"file": ("cheque.pdf", b"%PDF", "application/pdf")},
    )
    assert r.status_code == 201, r.text
    # All cheque-row uploads are cheque copies now, not bank letters.
    assert r.json()["attachment"]["is_bank_return_letter"] is False


def test_bank_return_letter_is_a_valid_case_category(client) -> None:
    """Phase 38: Bank Return Letter joins the fixed category list
    so it shows up as its own tile on the case Attachments grid."""
    assert CATEGORY_BANK_RETURN_LETTER in ATTACHMENT_CATEGORIES

    c, _ = client
    h = _h(c)
    case = _make_case_with_blank_cheque(c, h, code="P38-0004").json()
    r = c.post(
        f"/api/v1/cases/{case['id']}/attachments",
        headers=h,
        files={"file": ("return.pdf", b"%PDF-RET", "application/pdf")},
        data={"category": CATEGORY_BANK_RETURN_LETTER},
    )
    assert r.status_code == 201, r.text
    assert r.json()["category"] == CATEGORY_BANK_RETURN_LETTER
