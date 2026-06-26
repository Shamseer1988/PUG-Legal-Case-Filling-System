"""Phase 13 tests: closure flow + ZIP attachments + cash-flow report."""

import io
import zipfile

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
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("STORAGE_LOCAL_PATH", str(tmp_path / "storage"))
    monkeypatch.setenv("BACKUP_LOCAL_PATH", str(tmp_path / "backups"))
    monkeypatch.setenv("SMTP_HOST", "")
    (tmp_path / "storage").mkdir()
    (tmp_path / "backups").mkdir()

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

    orig = session_mod.SessionLocal
    session_mod.SessionLocal = TestingSessionLocal
    try:
        run_seed()
        yield TestClient(app)
    finally:
        session_mod.SessionLocal = orig
        app.dependency_overrides.clear()


def _login(client: TestClient) -> dict[str, str]:
    r = client.post(
        "/api/v1/auth/login",
        json={"email": DEFAULT_ADMIN_EMAIL, "password": DEFAULT_ADMIN_PASSWORD},
    )
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _approved_case(client: TestClient, h: dict[str, str]) -> dict:
    divs = client.get("/api/v1/masters/divisions", headers=h).json()
    cust = client.post(
        "/api/v1/masters/customers",
        headers=h,
        json={"code": "CLZ", "name": "Closure Test", "division_id": divs[0]["id"]},
    ).json()
    banks = client.get("/api/v1/masters/banks", headers=h).json()
    case = client.post(
        "/api/v1/cases",
        headers=h,
        json={
            "customer_id": cust["id"],
            "division_id": divs[0]["id"],
            "is_civil": True,
            "legal_filing_amount": "9000.00",
            "cheques": [
                {
                    "cheque_number": "CL-1",
                    "bank_id": banks[0]["id"],
                    "amount": "9000.00",
                    "cheque_type": "Normal",
                }
            ],
        },
    ).json()
    from tests.conftest import attach_default_signatory
    attach_default_signatory(client, h, case["id"])
    client.post(f"/api/v1/cases/{case['id']}/submit", headers=h)
    for _ in range(6):
        client.post(
            f"/api/v1/cases/{case['id']}/transition",
            headers=h,
            json={"action": "approve", "comment": "ok"},
        )
    return case


def test_close_via_court_cheque(client: TestClient) -> None:
    h = _login(client)
    case = _approved_case(client, h)
    r = client.post(
        f"/api/v1/cases/{case['id']}/close",
        headers=h,
        json={
            "closure_type": "court_cheque",
            "command": "Court delivered cheque on schedule.",
            "settled_amount": "9000.00",
            "settled_date": "2026-06-15",
            "court_cheque_number": "CRT-001",
            "court_cheque_bank": "Emirates NBD",
            "court_cheque_date": "2026-06-15",
        },
    )
    assert r.status_code == 201, r.text
    cur = client.get(f"/api/v1/cases/{case['id']}", headers=h).json()
    assert cur["status"] == "Closed"
    closure = client.get(f"/api/v1/cases/{case['id']}/closure", headers=h).json()
    assert closure["closure_type"] == "court_cheque"
    assert closure["court_cheque_number"] == "CRT-001"


def test_close_requires_type_specific_field(client: TestClient) -> None:
    h = _login(client)
    case = _approved_case(client, h)
    r = client.post(
        f"/api/v1/cases/{case['id']}/close",
        headers=h,
        json={
            "closure_type": "online_transfer",
            "command": "Funds wired",
            "transfer_reference": "",  # missing
        },
    )
    assert r.status_code == 400


def test_close_before_approval_rejected(client: TestClient) -> None:
    h = _login(client)
    divs = client.get("/api/v1/masters/divisions", headers=h).json()
    cust = client.post(
        "/api/v1/masters/customers",
        headers=h,
        json={"code": "EARLY", "name": "Early Close", "division_id": divs[0]["id"]},
    ).json()
    banks = client.get("/api/v1/masters/banks", headers=h).json()
    case = client.post(
        "/api/v1/cases",
        headers=h,
        json={
            "customer_id": cust["id"],
            "division_id": divs[0]["id"],
            "is_civil": True,
            "cheques": [
                {"cheque_number": "x", "bank_id": banks[0]["id"], "amount": "1", "cheque_type": "Normal"}
            ],
        },
    ).json()
    r = client.post(
        f"/api/v1/cases/{case['id']}/close",
        headers=h,
        json={
            "closure_type": "cash_received",
            "command": "Nope",
            "cash_receipt_no": "1",
        },
    )
    assert r.status_code == 400


def test_attachments_zip(client: TestClient) -> None:
    h = _login(client)
    case = _approved_case(client, h)
    # Upload two attachments (PDF with the real magic prefix so the
    # upload-validation gate accepts them).
    for name in ("a.pdf", "b.pdf"):
        files = {"file": (name, io.BytesIO(b"%PDF-1.4 hello " + name.encode()), "application/pdf")}
        r = client.post(
            f"/api/v1/cases/{case['id']}/attachments",
            headers=h,
            files=files,
            data={"category": "Test"},
        )
        assert r.status_code == 201, r.text

    r = client.get(f"/api/v1/cases/{case['id']}/attachments.zip", headers=h)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    names = zf.namelist()
    assert "manifest.tsv" in names
    assert "a.pdf" in names
    assert "b.pdf" in names


def test_case_cash_flow_report(client: TestClient) -> None:
    h = _login(client)
    case = _approved_case(client, h)
    body = client.get(
        f"/api/v1/reports/case_cash_flow?case_no={case['case_no']}",
        headers=h,
    ).json()
    assert body["title"].startswith("Cash Flow")
    assert body["case"]["case_no"] == case["case_no"]
    # Must include the create + 6 approval transitions + at least 1 cheque row
    actions = {r["phase"] for r in body["rows"]}
    assert "Creation" in actions
    assert "Workflow" in actions
    assert "Cheque" in actions


def test_report_division_filter(client: TestClient) -> None:
    h = _login(client)
    _approved_case(client, h)
    divs = client.get("/api/v1/masters/divisions", headers=h).json()
    other_div = divs[1]["id"] if len(divs) > 1 else None
    if other_div:
        body = client.get(
            f"/api/v1/reports/case_register?division_id={other_div}", headers=h
        ).json()
        # That division has no cases yet
        assert body["rows"] == []
