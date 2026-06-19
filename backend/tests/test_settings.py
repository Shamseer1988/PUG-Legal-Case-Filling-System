"""Phase 10 tests: settings groups, sensitive masking, SMTP override, diagnostics."""

import base64
import os

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
    monkeypatch.setenv(
        "BACKUP_ENCRYPTION_KEY", base64.b64encode(os.urandom(32)).decode()
    )
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


def test_groups_descriptor(client: TestClient) -> None:
    h = _login(client)
    groups = client.get("/api/v1/settings/groups", headers=h).json()
    keys = {g["key"] for g in groups}
    assert {
        "company", "smtp", "ai", "numbering", "workflow", "security",
        "backup", "notifications", "appearance", "integrations", "data",
        "maintenance",
    } <= keys
    assert len(groups) == 12


def test_update_smtp_and_round_trip(client: TestClient) -> None:
    h = _login(client)
    payload = {
        "values": {
            "smtp.host": "smtp.example.com",
            "smtp.port": 2525,
            "smtp.use_tls": True,
            "smtp.username": "svc",
            "smtp.password": "super-secret",
            "smtp.from_email": "alerts@pug.local",
            "smtp.from_name": "PUG Alerts",
        }
    }
    r = client.put("/api/v1/settings/groups/smtp", headers=h, json=payload)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["smtp.host"] == "smtp.example.com"
    assert out["smtp.port"] == 2525
    # Sensitive password is masked in the response
    assert out["smtp.password"] == "********"


def test_sensitive_value_is_encrypted_at_rest(client: TestClient) -> None:
    h = _login(client)
    client.put(
        "/api/v1/settings/groups/integrations",
        headers=h,
        json={"values": {"integrations.s3_secret_key": "AKIA-secret-XYZ"}},
    )
    # Check the raw row in DB has the ENC: prefix
    from app.db import session as session_mod
    from app.models.settings import SettingsKV

    db = session_mod.SessionLocal()
    try:
        row = (
            db.query(SettingsKV)
            .filter(SettingsKV.key == "integrations.s3_secret_key")
            .first()
        )
        assert row is not None
        assert row.value.startswith("ENC:")
        # And it definitely isn't the plaintext
        assert "AKIA-secret-XYZ" not in row.value
    finally:
        db.close()


def test_unknown_field_rejected(client: TestClient) -> None:
    h = _login(client)
    r = client.put(
        "/api/v1/settings/groups/company",
        headers=h,
        json={"values": {"company.no_such_field": "x"}},
    )
    assert r.status_code == 400


def test_smtp_test_send_console_mode(client: TestClient) -> None:
    h = _login(client)
    r = client.post(
        "/api/v1/settings/smtp/test-send",
        headers=h,
        json={"to": "test@pug.local"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["status"] == "Sent"


def test_diagnostics(client: TestClient) -> None:
    h = _login(client)
    r = client.get("/api/v1/diagnostics", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    names = {c["name"] for c in body["checks"]}
    assert "Database" in names
    assert "Backup Encryption Key" in names
    # Database should report ok
    db_check = next(c for c in body["checks"] if c["name"] == "Database")
    assert db_check["ok"] is True
