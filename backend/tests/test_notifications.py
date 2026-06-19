"""Phase 5 tests: notifications fire on transitions and email log records them."""

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
    monkeypatch.setenv("SMTP_HOST", "")  # console mode

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


def _submit_case(client: TestClient, h: dict[str, str], with_sm: bool = True) -> int:
    divs = client.get("/api/v1/masters/divisions", headers=h).json()
    cust = client.post(
        "/api/v1/masters/customers",
        headers=h,
        json={"code": "NF1", "name": "Notify Cust", "division_id": divs[0]["id"]},
    ).json()
    banks = client.get("/api/v1/masters/banks", headers=h).json()
    users = client.get("/api/v1/users", headers=h).json()
    admin_id = users[0]["id"]
    payload = {
        "customer_id": cust["id"],
        "division_id": divs[0]["id"],
        "is_civil": True,
        "legal_filing_amount": "1000.00",
        "cheques": [
            {
                "cheque_number": "N-1",
                "bank_id": banks[0]["id"],
                "amount": "1000.00",
                "cheque_type": "Normal",
            }
        ],
    }
    if with_sm:
        payload["sales_manager_id"] = admin_id
    case = client.post("/api/v1/cases", headers=h, json=payload).json()
    client.post(f"/api/v1/cases/{case['id']}/submit", headers=h)
    return int(case["id"])


def test_notification_on_submit(client: TestClient) -> None:
    h = _login(client)
    _submit_case(client, h, with_sm=True)
    # Admin = the sales manager id we set
    notes = client.get("/api/v1/notifications", headers=h).json()
    assert any(n["event"] == "case.submitted" for n in notes)

    # Unread count > 0
    unread = client.get("/api/v1/notifications/unread-count", headers=h).json()
    assert unread["unread"] >= 1


def test_email_log_records_submission(client: TestClient) -> None:
    h = _login(client)
    _submit_case(client, h, with_sm=True)
    log = client.get("/api/v1/admin/email-log", headers=h).json()
    assert any(item["event"] == "case.submitted" for item in log)
    # console mode marks Sent
    assert all(item["status"] == "Sent" for item in log)


def test_mark_all_read(client: TestClient) -> None:
    h = _login(client)
    _submit_case(client, h)
    client.post("/api/v1/notifications/read-all", headers=h)
    unread = client.get("/api/v1/notifications/unread-count", headers=h).json()
    assert unread["unread"] == 0


def test_email_preview_and_resend(client: TestClient) -> None:
    h = _login(client)
    _submit_case(client, h)
    log_items = client.get("/api/v1/admin/email-log", headers=h).json()
    assert log_items
    lid = log_items[0]["id"]
    preview = client.get(f"/api/v1/admin/email-log/{lid}/preview", headers=h)
    assert preview.status_code == 200
    assert "Legal Case Control System" in preview.text
    r = client.post(f"/api/v1/admin/email-log/{lid}/resend", headers=h)
    assert r.status_code == 200
    assert r.json()["attempts"] >= 2
