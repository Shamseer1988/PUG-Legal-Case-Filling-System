"""Phase 7 tests: scheduled report CRUD + run-now + history."""

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


def _new_payload() -> dict:
    return {
        "name": "Weekly Case Register",
        "report_key": "case_register",
        "params": {},
        "cron": "0 9 * * 1",
        "timezone": "UTC",
        "recipients": ["chairman@pug.local"],
        "formats": ["pdf", "xlsx"],
        "notes": "Sent every Monday 9am UTC",
    }


def test_create_lists_and_computes_next_run(client: TestClient) -> None:
    h = _login(client)
    r = client.post("/api/v1/scheduled-reports", headers=h, json=_new_payload())
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["next_run_at"] is not None
    assert body["is_active"] is True

    listed = client.get("/api/v1/scheduled-reports", headers=h).json()
    assert any(s["id"] == body["id"] for s in listed)


def test_invalid_cron_rejected(client: TestClient) -> None:
    h = _login(client)
    bad = _new_payload() | {"cron": "not-a-cron-expression"}
    r = client.post("/api/v1/scheduled-reports", headers=h, json=bad)
    assert r.status_code == 400


def test_unknown_report_key_rejected(client: TestClient) -> None:
    h = _login(client)
    bad = _new_payload() | {"report_key": "no_such_report"}
    r = client.post("/api/v1/scheduled-reports", headers=h, json=bad)
    assert r.status_code == 400


def test_run_now_creates_history_and_email_log(client: TestClient) -> None:
    h = _login(client)
    s = client.post("/api/v1/scheduled-reports", headers=h, json=_new_payload()).json()
    r = client.post(f"/api/v1/scheduled-reports/{s['id']}/run-now", headers=h)
    assert r.status_code == 200, r.text
    run = r.json()
    assert run["status"] == "Success"
    assert run["email_log_id"] is not None

    hist = client.get(f"/api/v1/scheduled-reports/{s['id']}/history", headers=h).json()
    assert len(hist) == 1 and hist[0]["status"] == "Success"

    refreshed = client.get(f"/api/v1/scheduled-reports/{s['id']}", headers=h).json()
    assert refreshed["last_run_status"] == "Success"


def test_pause_and_resume(client: TestClient) -> None:
    h = _login(client)
    s = client.post("/api/v1/scheduled-reports", headers=h, json=_new_payload()).json()
    assert client.post(f"/api/v1/scheduled-reports/{s['id']}/pause", headers=h).json()["is_active"] is False
    assert client.post(f"/api/v1/scheduled-reports/{s['id']}/resume", headers=h).json()["is_active"] is True


def test_delete_schedule(client: TestClient) -> None:
    h = _login(client)
    s = client.post("/api/v1/scheduled-reports", headers=h, json=_new_payload()).json()
    r = client.delete(f"/api/v1/scheduled-reports/{s['id']}", headers=h)
    assert r.status_code == 204
    assert client.get(f"/api/v1/scheduled-reports/{s['id']}", headers=h).status_code == 404
