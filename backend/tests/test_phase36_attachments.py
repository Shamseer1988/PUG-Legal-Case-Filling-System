"""Phase 36: cheque attachments + OCR + view endpoint + ZIP + categories + case_no storage."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.attachment_categories import (
    ATTACHMENT_CATEGORIES,
    CATEGORY_CR_COPY,
    CATEGORY_OTHER,
    normalise_category,
)
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import *  # noqa: F401,F403
from app.models.case import Case, CaseAttachment, ChequeAttachment
from app.services import cheque_ocr, storage
from app.services.seed import DEFAULT_ADMIN_EMAIL, DEFAULT_ADMIN_PASSWORD, run_seed


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "p36.db"
    storage_dir = tmp_path / "storage"
    storage_dir.mkdir()
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("STORAGE_LOCAL_PATH", str(storage_dir))
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.delenv("OCR_VISION_API_KEY", raising=False)

    # ``settings`` was instantiated at import time so monkeypatching
    # the env var alone isn't enough - poke the attribute directly
    # so storage.py writes into tmp_path instead of the real project
    # storage folder.
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
        yield TestClient(app), TestingSessionLocal, storage_dir
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


_CUST_SEQ = [0]


def _make_case(c: TestClient, h: dict[str, str]) -> dict:
    divs = c.get("/api/v1/masters/divisions", headers=h).json()
    div_id = divs[0]["id"]
    banks = c.get("/api/v1/masters/banks", headers=h).json()
    _CUST_SEQ[0] += 1
    code = f"P36-{_CUST_SEQ[0]:03d}"
    cust = c.post(
        "/api/v1/masters/customers",
        headers=h,
        json={"code": code, "name": f"Phase 36 Co {code}", "division_id": div_id},
    ).json()
    case = c.post(
        "/api/v1/cases",
        headers=h,
        json={
            "customer_id": cust["id"],
            "division_id": div_id,
            "is_civil": True,
            # Index 0 = fully populated row that OCR must NOT clobber.
            # Index 1 = placeholder row with the bare minimum to pass
            #          validation; auto-fill is allowed to overwrite
            #          the bank/amount/date/bounce_reason here.
            "cheques": [
                {
                    "cheque_number": "CHQ-100",
                    "bank_id": banks[0]["id"],
                    "amount": "500.00",
                    "cheque_date": "2026-05-15",
                    "cheque_type": "Normal",
                    "bounce_reason": "Insufficient Funds",
                },
                {
                    "cheque_number": "TBD-1",
                    "bank_id": None,
                    "amount": "0",
                    "cheque_date": None,
                    "cheque_type": "Normal",
                    "bounce_reason": "",
                },
            ],
        },
    ).json()
    return case


# ============================== categories ==============================
def test_category_normaliser_collapses_unknown_to_other_docs() -> None:
    for cat in ATTACHMENT_CATEGORIES:
        assert normalise_category(cat) == cat
    # Legacy default is allowed through unchanged.
    assert normalise_category("Supporting Document") == "Supporting Document"
    # Anything else collapses to Other Docs.
    assert normalise_category("Invented Category") == CATEGORY_OTHER
    assert normalise_category(None) == CATEGORY_OTHER


def test_upload_attachment_clamps_category(client) -> None:
    c, SessionLocal, _ = client
    h = _admin_h(c)
    case = _make_case(c, h)
    r = c.post(
        f"/api/v1/cases/{case['id']}/attachments",
        headers=h,
        files={"file": ("crcopy.pdf", b"%PDF-FAKE", "application/pdf")},
        data={"category": CATEGORY_CR_COPY},
    )
    assert r.status_code == 201, r.text
    assert r.json()["category"] == CATEGORY_CR_COPY

    # Bogus category must collapse to Other Docs, not raise.
    r2 = c.post(
        f"/api/v1/cases/{case['id']}/attachments",
        headers=h,
        files={"file": ("misc.txt", b"hello", "text/plain")},
        data={"category": "Free-Form Made-Up"},
    )
    assert r2.status_code == 201, r2.text
    assert r2.json()["category"] == CATEGORY_OTHER


# ============================== storage layout ==============================
def test_attachment_lands_under_case_no_folder(client) -> None:
    """Phase 36 storage path uses the human-readable ``case_no``."""
    c, _, storage_dir = client
    h = _admin_h(c)
    case = _make_case(c, h)
    r = c.post(
        f"/api/v1/cases/{case['id']}/attachments",
        headers=h,
        files={"file": ("a.pdf", b"%PDF-1", "application/pdf")},
        data={"category": "Credit Application"},
    )
    assert r.status_code == 201, r.text
    safe = case["case_no"].replace("/", "_")
    case_dir = storage_dir / "cases" / safe
    assert case_dir.exists(), list((storage_dir / "cases").iterdir())
    assert any(case_dir.iterdir())


def test_legacy_case_id_folder_is_migrated_on_next_upload(client) -> None:
    """If a pre-Phase-36 ``<case_id>/`` folder exists, the next
    write moves it under the case_no name."""
    c, SessionLocal, storage_dir = client
    h = _admin_h(c)
    case = _make_case(c, h)
    legacy_dir = storage_dir / "cases" / str(case["id"])
    legacy_dir.mkdir(parents=True, exist_ok=True)
    (legacy_dir / "legacy.bin").write_bytes(b"legacy file")

    # The next upload triggers ensure_case_dir which renames the folder.
    r = c.post(
        f"/api/v1/cases/{case['id']}/attachments",
        headers=h,
        files={"file": ("fresh.pdf", b"%PDF-NEW", "application/pdf")},
    )
    assert r.status_code == 201, r.text
    safe = case["case_no"].replace("/", "_")
    target = storage_dir / "cases" / safe
    assert target.exists()
    assert (target / "legacy.bin").exists()
    assert not legacy_dir.exists()


# ============================== view endpoint ==============================
def test_case_attachment_view_uses_inline_disposition(client) -> None:
    c, _, _ = client
    h = _admin_h(c)
    case = _make_case(c, h)
    r = c.post(
        f"/api/v1/cases/{case['id']}/attachments",
        headers=h,
        files={"file": ("view.pdf", b"%PDF-VIEW", "application/pdf")},
    )
    aid = r.json()["id"]
    view = c.get(f"/api/v1/cases/{case['id']}/attachments/{aid}/view", headers=h)
    assert view.status_code == 200
    assert "inline" in view.headers["content-disposition"]
    dl = c.get(f"/api/v1/cases/{case['id']}/attachments/{aid}/download", headers=h)
    assert "attachment" in dl.headers["content-disposition"]


# ============================== cheque attachment + OCR ==============================
def test_upload_cheque_attachment_without_ocr_engine(client) -> None:
    """No Tesseract installed + no Vision LLM key = OCR returns
    success=False with a friendly warning but the upload still
    works and the file lands on disk."""
    c, SessionLocal, _ = client
    h = _admin_h(c)
    case = _make_case(c, h)
    cheque_id = c.get(f"/api/v1/cases/{case['id']}", headers=h).json()["cheques"][1][
        "id"
    ]

    r = c.post(
        f"/api/v1/cases/{case['id']}/cheques/{cheque_id}/attachments",
        headers=h,
        files={"file": ("letter.png", b"PNGDATA", "image/png")},
        data={"is_bank_return_letter": "true"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["attachment"]["cheque_id"] == cheque_id
    assert body["attachment"]["is_bank_return_letter"] is True
    # OCR couldn't extract anything in this minimal env - that's
    # the documented graceful-fallback path.
    assert body["ocr"]["success"] is False


def test_upload_cheque_attachment_applies_ocr_fields(client, monkeypatch) -> None:
    """When the OCR engine returns values, the cheque row is
    auto-filled in place and the API echoes the same values."""
    c, SessionLocal, _ = client
    h = _admin_h(c)
    case = _make_case(c, h)
    cheque_id = c.get(f"/api/v1/cases/{case['id']}", headers=h).json()["cheques"][1][
        "id"
    ]

    from datetime import date
    from decimal import Decimal

    def fake_extract(db, *, blob, mime):
        return cheque_ocr.ChequeOcrResult(
            success=True,
            engine="fake",
            cheque_number="AUTO-9001",
            bank_id=None,
            bank_name="Emirates NBD",
            amount=Decimal("12345.67"),
            cheque_date=date(2026, 7, 1),
            cheque_type="Normal",
            bounce_reason="INSUFFICIENT BALANCE",
        )

    monkeypatch.setattr(cheque_ocr, "extract_fields", fake_extract)

    r = c.post(
        f"/api/v1/cases/{case['id']}/cheques/{cheque_id}/attachments",
        headers=h,
        files={"file": ("letter.pdf", b"%PDF-LET", "application/pdf")},
        data={"is_bank_return_letter": "true"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["ocr"]["cheque_number"] == "AUTO-9001"
    assert body["ocr"]["amount"] == "12345.67"
    assert body["ocr"]["cheque_date"] == "2026-07-01"

    # Cheque row was updated in place (it started empty).
    fresh = c.get(f"/api/v1/cases/{case['id']}", headers=h).json()
    target = [ch for ch in fresh["cheques"] if ch["id"] == cheque_id][0]
    assert target["cheque_number"] == "AUTO-9001"
    assert target["amount"] == "12345.67"
    assert target["cheque_date"] == "2026-07-01"
    assert "INSUFFICIENT" in target["bounce_reason"]


def test_upload_with_is_bank_return_false_skips_ocr(client, monkeypatch) -> None:
    """If the operator unticks "this is a bank return letter" the
    OCR pipeline is skipped entirely - the file lands but the
    cheque row is untouched even if OCR would have found values."""
    c, SessionLocal, _ = client
    h = _admin_h(c)
    case = _make_case(c, h)
    cheque_id = c.get(f"/api/v1/cases/{case['id']}", headers=h).json()["cheques"][0][
        "id"
    ]

    from datetime import date
    from decimal import Decimal

    called = {"n": 0}

    def fake_extract(db, *, blob, mime):
        called["n"] += 1
        return cheque_ocr.ChequeOcrResult(
            success=True,
            engine="fake",
            cheque_number="OCR-WOULD-OVERWRITE",
            amount=Decimal("99999.99"),
            cheque_date=date(2099, 1, 1),
            bounce_reason="OCR_REASON",
        )

    monkeypatch.setattr(cheque_ocr, "extract_fields", fake_extract)

    c.post(
        f"/api/v1/cases/{case['id']}/cheques/{cheque_id}/attachments",
        headers=h,
        files={"file": ("misc.pdf", b"%PDF-LET", "application/pdf")},
        data={"is_bank_return_letter": "false"},
    )

    assert called["n"] == 0, "OCR was called even though flag was off"
    fresh = c.get(f"/api/v1/cases/{case['id']}", headers=h).json()
    target = [ch for ch in fresh["cheques"] if ch["id"] == cheque_id][0]
    # Original values from _make_case survive.
    assert target["cheque_number"] == "CHQ-100"
    assert target["amount"] == "500.00"
    assert target["cheque_date"] == "2026-05-15"
    assert "Insufficient" in target["bounce_reason"]


def test_list_and_view_and_delete_cheque_attachment(client) -> None:
    c, _, _ = client
    h = _admin_h(c)
    case = _make_case(c, h)
    cheque_id = c.get(f"/api/v1/cases/{case['id']}", headers=h).json()["cheques"][0][
        "id"
    ]
    up = c.post(
        f"/api/v1/cases/{case['id']}/cheques/{cheque_id}/attachments",
        headers=h,
        files={"file": ("scan.pdf", b"%PDF-S", "application/pdf")},
        data={"is_bank_return_letter": "false"},
    )
    assert up.status_code == 201, up.text
    aid = up.json()["attachment"]["id"]

    rows = c.get(
        f"/api/v1/cases/{case['id']}/cheques/{cheque_id}/attachments", headers=h
    ).json()
    assert len(rows) == 1 and rows[0]["id"] == aid

    view = c.get(
        f"/api/v1/cases/{case['id']}/cheques/{cheque_id}/attachments/{aid}/view",
        headers=h,
    )
    assert view.status_code == 200
    assert "inline" in view.headers["content-disposition"]

    dl = c.get(
        f"/api/v1/cases/{case['id']}/cheques/{cheque_id}/attachments/{aid}/download",
        headers=h,
    )
    assert dl.status_code == 200
    assert dl.content == b"%PDF-S"

    rm = c.delete(
        f"/api/v1/cases/{case['id']}/cheques/{cheque_id}/attachments/{aid}",
        headers=h,
    )
    assert rm.status_code == 204
    assert (
        c.get(
            f"/api/v1/cases/{case['id']}/cheques/{cheque_id}/attachments",
            headers=h,
        ).json()
        == []
    )


def test_cheque_attachment_404_when_cheque_belongs_to_other_case(client) -> None:
    c, _, _ = client
    h = _admin_h(c)
    case_a = _make_case(c, h)
    case_b = _make_case(c, h)
    cheque_in_b = c.get(f"/api/v1/cases/{case_b['id']}", headers=h).json()["cheques"][0][
        "id"
    ]
    # Cheque from case B addressed via case A => 404
    r = c.post(
        f"/api/v1/cases/{case_a['id']}/cheques/{cheque_in_b}/attachments",
        headers=h,
        files={"file": ("x.pdf", b"%PDF-X", "application/pdf")},
        data={"is_bank_return_letter": "false"},
    )
    assert r.status_code == 404


# ============================== ZIP ==============================
def test_zip_includes_case_and_cheque_attachments(client) -> None:
    c, _, _ = client
    h = _admin_h(c)
    case = _make_case(c, h)
    cheque_id = c.get(f"/api/v1/cases/{case['id']}", headers=h).json()["cheques"][0][
        "id"
    ]

    c.post(
        f"/api/v1/cases/{case['id']}/attachments",
        headers=h,
        files={"file": ("credit.pdf", b"%PDF-CR", "application/pdf")},
        data={"category": "Credit Application"},
    )
    c.post(
        f"/api/v1/cases/{case['id']}/cheques/{cheque_id}/attachments",
        headers=h,
        files={"file": ("bank-letter.pdf", b"%PDF-BANK", "application/pdf")},
        data={"is_bank_return_letter": "false"},
    )

    zr = c.get(f"/api/v1/cases/{case['id']}/attachments.zip", headers=h)
    assert zr.status_code == 200
    z = zipfile.ZipFile(io.BytesIO(zr.content))
    names = set(z.namelist())
    assert "credit.pdf" in names
    assert "cheques/cheque-1/bank-letter.pdf" in names
    assert "manifest.tsv" in names
    manifest = z.read("manifest.tsv").decode("utf-8")
    assert "credit.pdf" in manifest
    assert "bank-letter.pdf" in manifest


# ============================== OCR engine fallback ==============================
def test_ocr_with_no_engine_returns_failure_not_exception(client) -> None:
    """The host has no Tesseract installed in the test env. The
    pipeline must surface that cleanly."""
    c, SessionLocal, _ = client
    db = SessionLocal()
    try:
        res = cheque_ocr.extract_fields(db, blob=b"PNGDATA", mime="image/png")
        assert res.success is False
        assert any("OCR engine" in w or "no text" in w.lower() for w in res.warnings)
    finally:
        db.close()


def test_ocr_text_extraction_pulls_fields_via_regex(client) -> None:
    """The regex extractor is exercised directly so we don't need
    a real Tesseract install to test field parsing."""
    c, SessionLocal, _ = client
    db = SessionLocal()
    try:
        text = (
            "BANK RETURN ADVICE\n"
            "Bank: Emirates NBD\n"
            "Cheque No.: CH-AB-1234\n"
            "Amount: AED 1,250.75\n"
            "Date: 2026-05-15\n"
            "Reason for return: Insufficient Balance\n"
        )
        res = cheque_ocr._extract_from_text(db, text, engine="test")
        assert res.success is True
        assert res.cheque_number == "CH-AB-1234"
        assert str(res.amount) == "1250.75"
        assert res.cheque_date.isoformat() == "2026-05-15"
        assert "Insufficient" in res.bounce_reason
        assert res.bank_name == "Emirates NBD"
        assert res.bank_id is not None
    finally:
        db.close()
