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
from .conftest import attach_default_signatory
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
    # Phase 40: submit also requires at least one cheque signatory.
    attach_default_signatory(c, h, case)
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


def test_ocr_no_engine_warning_is_actionable(client) -> None:
    """When no engine is available, the warning must tell the
    operator what to do (set OCR_VISION_API_KEY or install
    Tesseract) - not just "OCR failed"."""
    from app.services import cheque_ocr

    c, SessionLocal = client
    db = SessionLocal()
    try:
        res = cheque_ocr.extract_fields(db, blob=b"PNGDATA", mime="image/png")
        assert res.success is False
        joined = " ".join(res.warnings).lower()
        assert "ocr_vision_api_key" in joined or "tesseract" in joined
    finally:
        db.close()


def test_ocr_handles_qatar_commercial_bank_layout(client) -> None:
    """Regression coverage for the user-supplied Commercial Bank
    of Qatar cheque: bilingual layout, asterisk-wrapped amount,
    DD-MM-YYYY date, label and number on different lines."""
    from app.services import cheque_ocr

    c, SessionLocal = client
    db = SessionLocal()
    try:
        # Roughly what Tesseract would extract from the user's
        # cheque - labels and values typically land on adjacent
        # lines, the amount is between asterisks, the bank name
        # appears in the header.
        text = (
            "COMMERCIAL BANK\n"
            "The Commercial Bank (P.S.Q.C.)\n"
            "Cheque No.\n"
            "01001197\n"
            "Date 23-06-2026\n"
            "Pay HAK CORPORATE B\n"
            "Eighty Thousand Only\n"
            "QR **80,000.00**\n"
        )
        res = cheque_ocr._extract_from_text(db, text, engine="test")
        # cheque number arrives via the bare-number fallback
        assert res.cheque_number == "01001197"
        # amount arrives via the asterisk-wrapped pattern
        assert str(res.amount) == "80000.00"
        # date is the DD-MM-YYYY form
        assert res.cheque_date.isoformat() == "2026-06-23"
        # bank-hint regex now covers "Commercial Bank"
        assert res.bank_name and "commercial" in res.bank_name.lower()
        # bounce_reason is never populated from a cheque image
        assert res.bounce_reason is None
    finally:
        db.close()


def test_cheque_attachments_survive_a_case_patch(client) -> None:
    """The bug the user reported: every PATCH on a case used to
    clear and rebuild the cheque rows, which cascade-deleted any
    attached cheque copies. After Phase 38 diff-merge, attachments
    must survive untouched."""
    from app.models.case import Cheque, ChequeAttachment

    c, SessionLocal = client
    h = _h(c)
    case = _make_case_with_blank_cheque(c, h, code="P38-0005").json()
    case_id = case["id"]
    cheque_id = case["cheques"][0]["id"]

    # Attach a fake cheque copy to the row.
    up = c.post(
        f"/api/v1/cases/{case_id}/cheques/{cheque_id}/attachments",
        headers=h,
        files={"file": ("scan.pdf", b"%PDF-SCAN", "application/pdf")},
    )
    assert up.status_code == 201, up.text
    att_id = up.json()["attachment"]["id"]

    # PATCH the case - send the same cheque row back with its id
    # set, plus a brand-new second row (no id).
    patch = c.patch(
        f"/api/v1/cases/{case_id}",
        headers=h,
        json={
            "commands": "After-save smoke test",
            "cheques": [
                {
                    "id": cheque_id,
                    "cheque_number": "FILLED-AFTER-PATCH",
                    "bank_id": None,
                    "amount": "1.00",
                    "cheque_date": "2026-05-15",
                    "cheque_type": "Normal",
                    "bounce_reason": "Insufficient Funds",
                },
                {
                    # No id => brand new row
                    "cheque_number": "NEW-2",
                    "bank_id": None,
                    "amount": "2.00",
                    "cheque_date": "2026-05-16",
                    "cheque_type": "Normal",
                    "bounce_reason": "",
                },
            ],
        },
    )
    assert patch.status_code == 200, patch.text

    # The original cheque row keeps its id AND its attachment.
    db = SessionLocal()
    try:
        same_cheque = db.get(Cheque, cheque_id)
        assert same_cheque is not None, "diff-merge should have kept the row"
        assert same_cheque.cheque_number == "FILLED-AFTER-PATCH"

        same_att = db.get(ChequeAttachment, att_id)
        assert same_att is not None, (
            "ChequeAttachment was cascade-deleted - PATCH still rebuilds the rows"
        )
        assert same_att.cheque_id == cheque_id

        # And the brand-new row was added.
        all_cheques = list(same_cheque.case.cheques)
        assert len(all_cheques) == 2
        assert any(ch.cheque_number == "NEW-2" for ch in all_cheques)
    finally:
        db.close()


def test_patch_with_missing_cheque_id_deletes_the_row(client) -> None:
    """Diff-merge also has to handle removal: a cheque whose id is
    not in the payload should be deleted along with its files."""
    from app.models.case import Cheque, ChequeAttachment

    c, SessionLocal = client
    h = _h(c)
    case = _make_case_with_blank_cheque(c, h, code="P38-0006").json()
    case_id = case["id"]
    cheque_id = case["cheques"][0]["id"]

    up = c.post(
        f"/api/v1/cases/{case_id}/cheques/{cheque_id}/attachments",
        headers=h,
        files={"file": ("scan.pdf", b"%PDF", "application/pdf")},
    )
    att_id = up.json()["attachment"]["id"]

    # PATCH with an EMPTY cheques list - the existing row should go.
    patch = c.patch(
        f"/api/v1/cases/{case_id}",
        headers=h,
        json={"cheques": []},
    )
    assert patch.status_code == 200, patch.text

    db = SessionLocal()
    try:
        assert db.get(Cheque, cheque_id) is None
        # Attachment cascades away with the cheque - that's the
        # expected behaviour when the user actually removes the row.
        assert db.get(ChequeAttachment, att_id) is None
    finally:
        db.close()


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
