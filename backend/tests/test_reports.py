"""Phase 6 tests: report JSON + Excel/PDF renderers."""

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
    monkeypatch.setenv("SMTP_HOST", "")

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


def _seed_one_case(client: TestClient, h: dict[str, str]) -> int:
    divs = client.get("/api/v1/masters/divisions", headers=h).json()
    cust = client.post(
        "/api/v1/masters/customers",
        headers=h,
        json={"code": "R1", "name": "Reports Cust", "division_id": divs[0]["id"]},
    ).json()
    banks = client.get("/api/v1/masters/banks", headers=h).json()
    case = client.post(
        "/api/v1/cases",
        headers=h,
        json={
            "customer_id": cust["id"],
            "division_id": divs[0]["id"],
            "is_civil": True,
            "legal_filing_amount": "12000.00",
            "cheques": [
                {
                    "cheque_number": "R-1",
                    "bank_id": banks[0]["id"],
                    "amount": "12000.00",
                    "cheque_type": "Normal",
                }
            ],
        },
    ).json()
    client.post(f"/api/v1/cases/{case['id']}/submit", headers=h)
    return int(case["id"])


def test_report_registry(client: TestClient) -> None:
    h = _login(client)
    rs = client.get("/api/v1/reports", headers=h).json()
    keys = {r["key"] for r in rs}
    assert {"case_register", "status_summary", "aging_report", "division_summary"} <= keys


def test_case_register_json(client: TestClient) -> None:
    h = _login(client)
    _seed_one_case(client, h)
    r = client.get("/api/v1/reports/case_register", headers=h)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["title"] == "Case Register"
    assert any(row["case_no"].startswith("PUG-LEGAL-") for row in data["rows"])


def test_excel_export(client: TestClient) -> None:
    h = _login(client)
    _seed_one_case(client, h)
    r = client.get("/api/v1/reports/case_register.xlsx", headers=h)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml"
    )
    # XLSX files are zip archives starting with PK
    assert r.content[:2] == b"PK"
    assert len(r.content) > 2000


def test_pdf_export(client: TestClient) -> None:
    h = _login(client)
    _seed_one_case(client, h)
    r = client.get("/api/v1/reports/case_register.pdf", headers=h)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF"
    assert len(r.content) > 2000


def test_unknown_report_404(client: TestClient) -> None:
    h = _login(client)
    r = client.get("/api/v1/reports/no_such_report", headers=h)
    assert r.status_code == 404
