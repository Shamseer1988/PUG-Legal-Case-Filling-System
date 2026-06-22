"""Phase 35: admin scheduler-job monitor."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import *  # noqa: F401,F403
from app.models.job_run import JobRun
from app.services import job_monitor, scheduler_service
from app.services.seed import DEFAULT_ADMIN_EMAIL, DEFAULT_ADMIN_PASSWORD, run_seed


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "p35.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")

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
        yield TestClient(app), TestingSessionLocal
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


def test_record_writes_one_jobrun_per_tick(client) -> None:
    c, SessionLocal = client
    db = SessionLocal()
    try:
        with job_monitor.record(db, "test-job") as h:
            h.detail = "did some work"
        last = job_monitor.last_run(db, "test-job")
        assert last is not None
        assert last.ok is True
        assert last.detail == "did some work"
        assert last.finished_at is not None
        assert last.duration_ms >= 0
    finally:
        db.close()


def test_record_captures_exceptions(client) -> None:
    """A raised exception must still produce a failed JobRun row
    and propagate so APScheduler sees the failure."""
    c, SessionLocal = client
    db = SessionLocal()
    try:
        with pytest.raises(ValueError):
            with job_monitor.record(db, "boom"):
                raise ValueError("kaboom")
        last = job_monitor.last_run(db, "boom")
        assert last is not None
        assert last.ok is False
        assert "kaboom" in last.detail
    finally:
        db.close()


def test_prune_keeps_only_recent_rows(client) -> None:
    """The history is capped per job so the table doesn't grow
    forever (email queue ticks every 10s)."""
    c, SessionLocal = client
    db = SessionLocal()
    try:
        for _ in range(job_monitor.HISTORY_PER_JOB + 5):
            with job_monitor.record(db, "spammy") as h:
                h.detail = "."
        total = db.query(JobRun).filter(JobRun.job_id == "spammy").count()
        assert total == job_monitor.HISTORY_PER_JOB
    finally:
        db.close()


def test_admin_jobs_endpoint_lists_all_known_jobs(client) -> None:
    c, _ = client
    h = _admin_h(c)
    r = c.get("/api/v1/admin/jobs", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    ids = {row["job_id"] for row in body}
    # Every tick we manage must show up, even with no history yet.
    assert ids == set(scheduler_service.known_job_ids())
    # Without the scheduler running, every job reports running=False
    # and no next_run_at. The shape is what matters, not the values.
    for row in body:
        assert "interval_seconds" in row
        assert "last_run" in row
        assert "success_rate_recent" in row


def test_admin_jobs_history_endpoint(client) -> None:
    c, SessionLocal = client
    h = _admin_h(c)
    db = SessionLocal()
    try:
        for i in range(3):
            with job_monitor.record(db, scheduler_service.SLA_JOB_ID) as hh:
                hh.detail = f"run={i}"
    finally:
        db.close()

    r = c.get(
        f"/api/v1/admin/jobs/{scheduler_service.SLA_JOB_ID}/history",
        headers=h,
    )
    assert r.status_code == 200, r.text
    rows = r.json()
    assert len(rows) == 3
    # Newest first
    assert rows[0]["detail"] == "run=2"
    assert rows[-1]["detail"] == "run=0"


def test_admin_jobs_history_404_for_unknown_id(client) -> None:
    c, _ = client
    h = _admin_h(c)
    r = c.get("/api/v1/admin/jobs/not-a-real-job/history", headers=h)
    assert r.status_code == 404


def test_run_now_503_when_scheduler_not_running(client) -> None:
    """The TestClient fixture doesn't boot the scheduler, so
    run-now must report it gracefully instead of crashing."""
    c, _ = client
    h = _admin_h(c)
    r = c.post(
        f"/api/v1/admin/jobs/{scheduler_service.SLA_JOB_ID}/run-now",
        headers=h,
    )
    assert r.status_code == 503


def test_admin_jobs_requires_admin_settings(client) -> None:
    c, _ = client
    assert c.get("/api/v1/admin/jobs").status_code == 401
