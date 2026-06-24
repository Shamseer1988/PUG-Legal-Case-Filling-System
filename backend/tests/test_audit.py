"""Phase 8 audit log tests."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import *  # noqa: F401,F403
from app.models.audit import AuditLog
from app.services import audit_service
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


def _all_rows(client: TestClient, h: dict[str, str]) -> list[dict]:
    return client.get("/api/v1/audit-log?limit=1000", headers=h).json()


def test_login_records_audit(client: TestClient) -> None:
    # Successful login creates a "login" entry
    h = _login(client)
    rows = _all_rows(client, h)
    assert any(r["action"] == "login" for r in rows)


def test_failed_login_records_audit(client: TestClient) -> None:
    # Bad password creates a "login_failed" entry
    client.post(
        "/api/v1/auth/login",
        json={"email": DEFAULT_ADMIN_EMAIL, "password": "wrong"},
    )
    h = _login(client)
    rows = _all_rows(client, h)
    assert any(r["action"] == "login_failed" for r in rows)


def test_master_create_update_delete_audited(client: TestClient) -> None:
    h = _login(client)
    # Create
    r = client.post(
        "/api/v1/masters/banks",
        headers=h,
        json={"code": "TST", "name": "Test Bank"},
    )
    bank_id = r.json()["id"]
    # Update
    client.patch(
        f"/api/v1/masters/banks/{bank_id}",
        headers=h,
        json={"name": "Renamed Bank"},
    )
    # Delete
    client.delete(f"/api/v1/masters/banks/{bank_id}", headers=h)

    rows = _all_rows(client, h)
    actions_for_bank = [r["action"] for r in rows if r["entity_type"] == "Bank"]
    assert "create" in actions_for_bank
    assert "update" in actions_for_bank
    assert "delete" in actions_for_bank


def test_chain_verifies(client: TestClient) -> None:
    h = _login(client)
    # Create a couple of rows to grow the chain
    client.post(
        "/api/v1/masters/banks",
        headers=h,
        json={"code": "C1", "name": "Chain Bank 1"},
    )
    client.post(
        "/api/v1/masters/banks",
        headers=h,
        json={"code": "C2", "name": "Chain Bank 2"},
    )
    r = client.get("/api/v1/audit-log/verify", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["verified"] is True
    assert body["count"] >= 3  # at least login + 2 creates
    assert body["issues"] == []


def test_tamper_breaks_chain(tmp_path, monkeypatch, client: TestClient) -> None:
    h = _login(client)
    client.post(
        "/api/v1/masters/banks",
        headers=h,
        json={"code": "TMP", "name": "Tamper Test"},
    )
    # Locate the DB session and tamper with the latest row's summary
    from app.db import session as session_mod

    db = session_mod.SessionLocal()
    try:
        row = db.query(AuditLog).order_by(AuditLog.id.desc()).first()
        assert row is not None
        row.summary = "TAMPERED"
        db.commit()
    finally:
        db.close()

    body = client.get("/api/v1/audit-log/verify", headers=h).json()
    assert body["verified"] is False
    assert any(i["issue"] == "row_hash_mismatch" for i in body["issues"])


def test_csv_and_pdf_exports(client: TestClient) -> None:
    h = _login(client)
    client.post(
        "/api/v1/masters/banks",
        headers=h,
        json={"code": "EX", "name": "Export Bank"},
    )

    r = client.get("/api/v1/audit-log.csv", headers=h)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert b"row_hash" in r.content[:200]

    r = client.get("/api/v1/audit-log.pdf", headers=h)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF"


def test_filter_by_action(client: TestClient) -> None:
    h = _login(client)
    rows = client.get("/api/v1/audit-log?action=login", headers=h).json()
    assert rows and all(r["action"] == "login" for r in rows)
