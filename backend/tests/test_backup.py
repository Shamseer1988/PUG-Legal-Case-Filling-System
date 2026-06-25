"""Phase 9 tests: backup create / verify / restore / delete."""

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
from app.models.masters import Bank
from app.services.seed import DEFAULT_ADMIN_EMAIL, DEFAULT_ADMIN_PASSWORD, run_seed


def _key() -> str:
    return base64.b64encode(os.urandom(32)).decode()


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    storage_dir = tmp_path / "storage"
    backups_dir = tmp_path / "backups"
    storage_dir.mkdir()
    backups_dir.mkdir()
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("STORAGE_LOCAL_PATH", str(storage_dir))
    monkeypatch.setenv("BACKUP_LOCAL_PATH", str(backups_dir))
    monkeypatch.setenv("SMTP_HOST", "")
    monkeypatch.setenv("BACKUP_ENCRYPTION_KEY", _key())

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
    from app.services import seed as seed_mod

    orig_sl = session_mod.SessionLocal
    orig_seed_sl = seed_mod.SessionLocal
    session_mod.SessionLocal = TestingSessionLocal
    seed_mod.SessionLocal = TestingSessionLocal
    try:
        run_seed()
        yield TestClient(app)
    finally:
        session_mod.SessionLocal = orig_sl
        seed_mod.SessionLocal = orig_seed_sl
        app.dependency_overrides.clear()


def _login(client: TestClient) -> dict[str, str]:
    r = client.post(
        "/api/v1/auth/login",
        json={"email": DEFAULT_ADMIN_EMAIL, "password": DEFAULT_ADMIN_PASSWORD},
    )
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_create_backup_and_verify(client: TestClient) -> None:
    h = _login(client)
    r = client.post("/api/v1/backups", headers=h, json={"notes": "test"})
    assert r.status_code == 201, r.text
    job = r.json()
    assert job["status"] == "Completed"
    assert job["is_encrypted"] is True
    assert job["size_bytes"] > 0
    assert len(job["checksum_sha256"]) == 64
    assert "banks" in job["table_row_counts"]

    v = client.get(f"/api/v1/backups/{job['id']}/verify", headers=h).json()
    assert v["ok"] is True


def test_unencrypted_backup_when_no_key(client: TestClient, monkeypatch) -> None:
    from app.core.config import settings
    monkeypatch.setattr(settings, "backup_encryption_key", "")
    h = _login(client)
    r = client.post("/api/v1/backups", headers=h, json={"notes": "plain"})
    assert r.status_code == 201, r.text
    assert r.json()["is_encrypted"] is False
    v = client.get(f"/api/v1/backups/{r.json()['id']}/verify", headers=h).json()
    assert v["ok"] is True


def test_restore_round_trip(client: TestClient) -> None:
    h = _login(client)
    # Snapshot baseline
    r = client.post("/api/v1/backups", headers=h, json={"notes": "baseline"})
    bid = r.json()["id"]

    # Mutate: delete every seeded bank
    banks = client.get("/api/v1/masters/banks", headers=h).json()
    for b in banks:
        client.delete(f"/api/v1/masters/banks/{b['id']}", headers=h)
    assert client.get("/api/v1/masters/banks", headers=h).json() == []

    # Restore
    r = client.post(
        f"/api/v1/backups/{bid}/restore",
        headers=h,
        json={"confirmation": "RESTORE", "take_safety_snapshot": True},
    )
    assert r.status_code == 200, r.text
    rj = r.json()
    assert rj["status"] == "Completed"
    assert rj["safety_snapshot_id"] is not None

    # Banks are back
    h2 = _login(client)  # token still valid after restore
    after = client.get("/api/v1/masters/banks", headers=h2).json()
    assert len(after) == len(banks)


def test_restore_requires_confirmation(client: TestClient) -> None:
    h = _login(client)
    r = client.post("/api/v1/backups", headers=h, json={}).json()
    bad = client.post(
        f"/api/v1/backups/{r['id']}/restore",
        headers=h,
        json={"confirmation": "yes please"},
    )
    assert bad.status_code == 400


def test_delete_backup_removes_file(client: TestClient) -> None:
    from app.core.config import settings
    h = _login(client)
    r = client.post("/api/v1/backups", headers=h, json={}).json()
    backups_dir = settings.backup_path
    files_before = list(backups_dir.iterdir())
    assert any(f.name == r["storage_path"] for f in files_before)

    assert client.delete(f"/api/v1/backups/{r['id']}", headers=h).status_code == 204
    assert not (backups_dir / r["storage_path"]).exists()


def test_status_endpoint(client: TestClient) -> None:
    h = _login(client)
    client.post("/api/v1/backups", headers=h, json={})
    st = client.get("/api/v1/backups/status", headers=h).json()
    assert st["encryption_enabled"] is True
    assert st["backup_count"] >= 1
    assert st["total_size_bytes"] > 0
