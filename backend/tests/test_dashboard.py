"""Phase 11 dashboard tests."""

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


def _make_case(client: TestClient, h: dict[str, str]) -> int:
    divs = client.get("/api/v1/masters/divisions", headers=h).json()
    cust = client.post(
        "/api/v1/masters/customers",
        headers=h,
        json={"code": "DBC", "name": "Dashboard Cust", "division_id": divs[0]["id"]},
    ).json()
    banks = client.get("/api/v1/masters/banks", headers=h).json()
    case = client.post(
        "/api/v1/cases",
        headers=h,
        json={
            "customer_id": cust["id"],
            "division_id": divs[0]["id"],
            "is_civil": True,
            "legal_filing_amount": "5000.00",
            "cheques": [
                {
                    "cheque_number": "D-1",
                    "bank_id": banks[0]["id"],
                    "amount": "5000.00",
                    "cheque_type": "Normal",
                }
            ],
        },
    ).json()
    from tests.conftest import attach_default_signatory
    attach_default_signatory(client, h, case["id"])
    client.post(f"/api/v1/cases/{case['id']}/submit", headers=h)
    return int(case["id"])


def test_kpis_empty(client: TestClient) -> None:
    h = _login(client)
    k = client.get("/api/v1/dashboard/kpis", headers=h).json()
    assert k["total_cases"] == 0
    assert k["open_cases"] == 0
    assert k["pending_my_inbox"] == 0


def test_kpis_after_case(client: TestClient) -> None:
    h = _login(client)
    _make_case(client, h)
    k = client.get("/api/v1/dashboard/kpis", headers=h).json()
    assert k["total_cases"] == 1
    assert k["open_cases"] == 1
    # admin is super so they can act at the Sales Manager stage
    assert k["pending_my_inbox"] >= 1


def test_status_breakdown(client: TestClient) -> None:
    h = _login(client)
    _make_case(client, h)
    rows = client.get("/api/v1/dashboard/status-breakdown", headers=h).json()
    assert any(r["status"] == "Submitted" for r in rows)


def test_trend_returns_12_months(client: TestClient) -> None:
    h = _login(client)
    points = client.get("/api/v1/dashboard/trend", headers=h).json()
    assert len(points) == 12
    assert all("month" in p for p in points)


def test_division_heatmap(client: TestClient) -> None:
    h = _login(client)
    _make_case(client, h)
    rows = client.get("/api/v1/dashboard/division-heatmap", headers=h).json()
    assert rows
    row = rows[0]
    assert row["total"] == 1
    assert isinstance(row["by_status"], dict)


def test_alerts_empty_by_default(client: TestClient) -> None:
    h = _login(client)
    alerts = client.get("/api/v1/dashboard/alerts", headers=h).json()
    # Fresh case with future SLA - no alerts yet
    assert alerts == []
