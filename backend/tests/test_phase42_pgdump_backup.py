"""Phase 42 tests: pg_dump backup engine + Upload+Restore + R2 + settings.

The pg_dump pipeline itself is exercised in production (LXC Postgres);
under SQLite test runs we cover the format-dispatcher, the upload
validator, the settings round-trip, and the activity log.
"""

from __future__ import annotations

import base64
import io
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import *  # noqa: F401,F403
from app.models.backup import (
    BACKUP_FORMAT_LEGACY,
    BACKUP_FORMAT_PGDUMP,
)
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
    # SQLite for tests - pg_dump path is gated by pg_tools.is_postgres().
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("STORAGE_LOCAL_PATH", str(storage_dir))
    monkeypatch.setenv("BACKUP_LOCAL_PATH", str(backups_dir))
    monkeypatch.setenv("SMTP_HOST", "")
    monkeypatch.setenv("BACKUP_ENCRYPTION_KEY", _key())

    engine = create_engine(f"sqlite:///{db_path}", future=True)
    TSL = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(engine)

    def override_get_db():
        db = TSL()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    from app.db import session as session_mod
    from app.services import seed as seed_mod

    orig_sl = session_mod.SessionLocal
    orig_seed_sl = seed_mod.SessionLocal
    session_mod.SessionLocal = TSL
    seed_mod.SessionLocal = TSL
    try:
        run_seed()
        yield TestClient(app), tmp_path, TSL
    finally:
        session_mod.SessionLocal = orig_sl
        seed_mod.SessionLocal = orig_seed_sl
        app.dependency_overrides.clear()


def _login(c: TestClient) -> dict[str, str]:
    r = c.post(
        "/api/v1/auth/login",
        json={"email": DEFAULT_ADMIN_EMAIL, "password": DEFAULT_ADMIN_PASSWORD},
    )
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# ============================== format dispatcher ==============================
def test_create_backup_uses_legacy_path_on_sqlite(client) -> None:
    """The dispatcher must pick the legacy serialiser when the DB
    isn't Postgres - shells out to pg_dump would fail."""
    c, _, _ = client
    h = _login(c)
    r = c.post("/api/v1/backups", headers=h, json={"notes": "phase42 dispatcher"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["format"] == BACKUP_FORMAT_LEGACY
    assert body["storage_path"].endswith((".bkp.enc", ".bkp.tar.gz"))


# ============================== Upload + Restore ==============================
def test_upload_restore_rejects_non_dump_extension(client) -> None:
    c, _, _ = client
    h = _login(c)
    r = c.post(
        "/api/v1/backups/upload-restore?confirmation=RESTORE",
        headers=h,
        files={"file": ("backup.txt", io.BytesIO(b"hello"), "text/plain")},
    )
    assert r.status_code == 400, r.text
    assert ".dump" in r.json()["detail"]


def test_upload_restore_rejects_non_pgdump_blob(client) -> None:
    """Catches a renamed .txt / random binary masquerading as .dump
    before pg_restore mangles the live DB."""
    c, _, _ = client
    h = _login(c)
    r = c.post(
        "/api/v1/backups/upload-restore?confirmation=RESTORE",
        headers=h,
        files={
            "file": (
                "evil.dump",
                io.BytesIO(b"not a real pg_dump archive"),
                "application/octet-stream",
            )
        },
    )
    assert r.status_code == 400, r.text
    assert "pg_dump" in r.json()["detail"]


def test_upload_restore_requires_confirmation(client) -> None:
    c, _, _ = client
    h = _login(c)
    r = c.post(
        "/api/v1/backups/upload-restore?confirmation=NO",
        headers=h,
        files={"file": ("backup.dump", io.BytesIO(b"PGDMP" + b"\x00" * 8), "application/octet-stream")},
    )
    assert r.status_code == 400, r.text
    assert "RESTORE" in r.json()["detail"]


# ============================== Settings ==============================
def test_backup_settings_round_trip(client) -> None:
    c, _, _ = client
    h = _login(c)
    r = c.get("/api/v1/backups/settings", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    # Defaults exposed by the schema
    assert body["daily_enabled"] is False
    assert body["daily_time"] == "23:00"

    upd = c.put(
        "/api/v1/backups/settings",
        headers=h,
        json={
            "daily_enabled": True,
            "daily_time": "02:30",
            "weekly_enabled": True,
            "weekly_day": "Sunday",
            "weekly_time": "23:45",
            "cloud_provider": "cloudflare_r2",
            "cloud_folder": "s3://bucket/legal-backups",
        },
    )
    assert upd.status_code == 200, upd.text
    s = upd.json()
    assert s["daily_enabled"] is True
    assert s["daily_time"] == "02:30"
    assert s["weekly_day"] == "Sunday"
    assert s["cloud_provider"] == "cloudflare_r2"


def test_backup_settings_rejects_bad_time(client) -> None:
    c, _, _ = client
    h = _login(c)
    bad = c.put(
        "/api/v1/backups/settings",
        headers=h,
        json={"daily_time": "25:99"},
    )
    assert bad.status_code == 400, bad.text


def test_backup_settings_rejects_bad_day(client) -> None:
    c, _, _ = client
    h = _login(c)
    bad = c.put(
        "/api/v1/backups/settings",
        headers=h,
        json={"weekly_day": "Funday"},
    )
    assert bad.status_code == 400, bad.text


# ============================== Activity log ==============================
def test_activity_log_records_backup_and_delete(client) -> None:
    """Each create / delete writes a row to the activity log so the
    Backup & Restore screen's bottom panel has content."""
    c, _, _ = client
    h = _login(c)

    job = c.post("/api/v1/backups", headers=h, json={"notes": "activity-test"}).json()

    act = c.get("/api/v1/backups/activity", headers=h).json()
    # Legacy path doesn't write activity rows (only the new pg_dump
    # path does) - it would be wrong to fake one. Tracker validates
    # the *delete* path which is engine-agnostic.
    before = len(act)

    r = c.delete(f"/api/v1/backups/{job['id']}", headers=h)
    assert r.status_code == 204

    act = c.get("/api/v1/backups/activity", headers=h).json()
    assert len(act) == before + 1
    head = act[0]
    assert head["activity_type"] == "Delete"
    assert head["file_name"] == job["storage_path"]


# ============================== R2 ==============================
def test_r2_test_reports_unconfigured(client) -> None:
    """No R2 creds saved -> Test connection returns ok=False with a
    helpful message (not an HTTP 500)."""
    c, _, _ = client
    h = _login(c)
    r = c.post("/api/v1/backups/r2/test", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is False
    assert "configured" in body["message"].lower() or "boto3" in body["message"].lower()


def test_r2_list_empty_when_unconfigured(client) -> None:
    c, _, _ = client
    h = _login(c)
    r = c.get("/api/v1/backups/r2", headers=h)
    assert r.status_code == 200, r.text
    assert r.json() == []


# ============================== Status ==============================
def test_status_exposes_folder_and_writability(client) -> None:
    """New Phase 42 status fields drive the four colored stat cards
    on the Backup files panel."""
    c, _, _ = client
    h = _login(c)
    r = c.get("/api/v1/backups/status", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["folder"]
    assert body["folder_writable"] is True
    assert body["free_space_bytes"] >= 0
    assert body["backup_count"] == 0


# ============================== Legacy compatibility ==============================
def test_legacy_restore_dispatcher_routes_by_format(client) -> None:
    """Phase 42 dispatcher must call the legacy code path when a
    BackupJob is marked ``format=legacy_enc``, NOT the pg_dump
    path. We assert by verifying the legacy verifier accepts the
    file - the verifier's path branches on the same format flag.
    """
    c, _, _ = client
    h = _login(c)
    job = c.post(
        "/api/v1/backups", headers=h, json={"notes": "legacy-routing-test"}
    ).json()
    assert job["format"] == BACKUP_FORMAT_LEGACY

    # Verify uses the SAME dispatcher that restore does. If routing
    # is broken, verify would call the pg_dump magic-byte check on a
    # tar.gz blob and report "not pg_dump custom format".
    v = c.get(f"/api/v1/backups/{job['id']}/verify", headers=h).json()
    assert v["ok"] is True, v
    assert "legacy" in v["message"].lower()
