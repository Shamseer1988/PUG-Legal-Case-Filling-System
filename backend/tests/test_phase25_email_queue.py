"""Phase 25: async email queue + retry/backoff + persisted attachments."""

import io
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import *  # noqa: F401,F403
from app.models.notification import (
    EMAIL_STATUS_FAILED,
    EMAIL_STATUS_QUEUED,
    EMAIL_STATUS_SENT,
    EmailLog,
    EmailLogAttachment,
)
from app.services import email_service
from app.services.seed import DEFAULT_ADMIN_EMAIL, DEFAULT_ADMIN_PASSWORD, run_seed


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "p25.db"
    storage_dir = tmp_path / "storage"
    storage_dir.mkdir()
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("STORAGE_LOCAL_PATH", str(storage_dir))
    # Console-mode SMTP for the happy path tests; failure tests
    # monkeypatch _deliver directly so we don't depend on a host.
    monkeypatch.delenv("SMTP_HOST", raising=False)

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


def test_queue_email_does_not_hit_smtp(client) -> None:
    """queue_email must just insert + commit. It must NOT call
    _deliver - that's the scheduler's job."""
    _c, SessionLocal = client
    delivered: list[int] = []

    orig_deliver = email_service._deliver

    def spy(db, log):
        delivered.append(log.id)
        return orig_deliver(db, log)

    email_service._deliver = spy
    try:
        db = SessionLocal()
        try:
            log = email_service.queue_email(
                db,
                to_emails=["dest@example.com"],
                subject="hello",
                template="notification_email.html",
                context={"title": "hello", "lines": ["body"]},
            )
            assert log.status == EMAIL_STATUS_QUEUED
            assert log.next_attempt_at is not None
            assert delivered == [], "queue_email must not call _deliver"
        finally:
            db.close()
    finally:
        email_service._deliver = orig_deliver


def test_process_queue_drains_console_mode_rows(client) -> None:
    _c, SessionLocal = client
    db = SessionLocal()
    try:
        email_service.queue_email(
            db,
            to_emails=["a@example.com"],
            subject="one",
            template="notification_email.html",
            context={"title": "one", "lines": []},
        )
        email_service.queue_email(
            db,
            to_emails=["b@example.com"],
            subject="two",
            template="notification_email.html",
            context={"title": "two", "lines": []},
        )

        stats = email_service.process_queue(db)
        assert stats["picked"] == 2
        assert stats["sent"] == 2
        rows = db.query(EmailLog).order_by(EmailLog.id).all()
        for r in rows:
            assert r.status == EMAIL_STATUS_SENT
            assert r.next_attempt_at is None
            assert r.attempts == 1
            assert r.sent_at is not None
    finally:
        db.close()


def test_attachments_round_trip(client) -> None:
    """Attachments are persisted on queue and re-attached on
    delivery (so resend keeps the original bytes)."""
    _c, SessionLocal = client
    db = SessionLocal()
    try:
        log = email_service.queue_email(
            db,
            to_emails=["c@example.com"],
            subject="with attachment",
            template="notification_email.html",
            context={"title": "x", "lines": []},
            attachments=[("report.pdf", b"%PDF-blob", "application/pdf")],
        )
        atts = db.query(EmailLogAttachment).filter_by(email_log_id=log.id).all()
        assert len(atts) == 1
        assert atts[0].filename == "report.pdf"
        assert atts[0].mime_type == "application/pdf"
        assert atts[0].content == b"%PDF-blob"
        assert atts[0].size_bytes == 9
    finally:
        db.close()


def test_failure_schedules_backoff_and_retains_status_queued(client, monkeypatch) -> None:
    """Simulate an SMTP failure on the first attempt: the row
    should stay Queued, attempts should be 1, and next_attempt_at
    should be in the future."""
    _c, SessionLocal = client
    db = SessionLocal()
    try:
        log = email_service.queue_email(
            db,
            to_emails=["d@example.com"],
            subject="fail-once",
            template="notification_email.html",
            context={"title": "fail-once", "lines": []},
        )
        # Force SMTP path by faking a host, then make smtplib raise.
        from app.services import settings_service as _ss
        monkeypatch.setattr(
            _ss,
            "effective_smtp",
            lambda _db: {
                "host": "smtp.invalid",
                "port": 25,
                "use_tls": False,
                "username": "",
                "password": "",
                "from_email": "from@example.com",
                "from_name": "Test",
            },
        )

        class _Fake1:
            def __init__(self, *a, **kw): raise OSError("connect refused")

        monkeypatch.setattr(email_service.smtplib, "SMTP", _Fake1)

        email_service._deliver(db, log)
        db.commit()
        db.refresh(log)
        assert log.attempts == 1
        assert log.status == EMAIL_STATUS_QUEUED, "still retryable"
        assert log.next_attempt_at is not None
        # SQLite returns naive datetimes; normalise to UTC for the
        # comparison. The real application code uses _utcnow() so
        # the value is correctly aware in production.
        nxt = log.next_attempt_at
        if nxt.tzinfo is None:
            nxt = nxt.replace(tzinfo=timezone.utc)
        assert nxt > datetime.now(timezone.utc)
        assert "connect refused" in log.error
    finally:
        db.close()


def test_exhausted_retries_park_in_failed(client, monkeypatch) -> None:
    """After MAX_ATTEMPTS failed deliveries the row is parked in
    status=Failed and next_attempt_at is cleared."""
    _c, SessionLocal = client
    db = SessionLocal()
    try:
        log = email_service.queue_email(
            db,
            to_emails=["e@example.com"],
            subject="always-fails",
            template="notification_email.html",
            context={"title": "always", "lines": []},
        )
        monkeypatch.setattr(
            email_service,
            "_schedule_retry",
            email_service._schedule_retry,
        )

        class _Fake:
            def __init__(self, *a, **kw): raise OSError("broken")

        monkeypatch.setattr(email_service.smtplib, "SMTP", _Fake)
        from app.services import settings_service as _ss
        monkeypatch.setattr(
            _ss,
            "effective_smtp",
            lambda _db: {
                "host": "smtp.invalid",
                "port": 25,
                "use_tls": False,
                "username": "",
                "password": "",
                "from_email": "f@example.com",
                "from_name": "T",
            },
        )
        for _ in range(email_service.MAX_ATTEMPTS):
            email_service._deliver(db, log)
            db.commit()
        db.refresh(log)
        assert log.status == EMAIL_STATUS_FAILED
        assert log.next_attempt_at is None
        assert log.attempts == email_service.MAX_ATTEMPTS
    finally:
        db.close()


def test_process_queue_respects_next_attempt_at(client) -> None:
    """A row whose next_attempt_at is in the future must NOT be
    drained by the worker yet."""
    _c, SessionLocal = client
    db = SessionLocal()
    try:
        log = email_service.queue_email(
            db,
            to_emails=["g@example.com"],
            subject="later",
            template="notification_email.html",
            context={"title": "later", "lines": []},
        )
        log.next_attempt_at = datetime.now(timezone.utc) + timedelta(minutes=10)
        db.commit()

        stats = email_service.process_queue(db)
        assert stats["picked"] == 0
        db.refresh(log)
        assert log.status == EMAIL_STATUS_QUEUED
    finally:
        db.close()


def test_resend_endpoint_requeues_and_clears_error(client) -> None:
    c, SessionLocal = client
    db = SessionLocal()
    try:
        log = email_service.queue_email(
            db,
            to_emails=["h@example.com"],
            subject="resend me",
            template="notification_email.html",
            context={"title": "resend", "lines": []},
        )
        log.status = EMAIL_STATUS_FAILED
        log.error = "old failure"
        log.next_attempt_at = None
        db.commit()
        log_id = log.id
    finally:
        db.close()

    h = _admin_h(c)
    r = c.post(f"/api/v1/admin/email-log/{log_id}/resend", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == EMAIL_STATUS_QUEUED
    assert body["error"] == ""


def test_send_test_email_endpoint_runs_inline(client) -> None:
    c, _SL = client
    h = _admin_h(c)
    r = c.post(
        "/api/v1/admin/email-log/test",
        headers=h,
        json={"to_email": "admin@example.com"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # Console mode means immediate Sent
    assert body["status"] == EMAIL_STATUS_SENT
    assert body["email_log_id"] > 0


def test_send_test_email_rejects_invalid_address(client) -> None:
    c, _SL = client
    h = _admin_h(c)
    r = c.post(
        "/api/v1/admin/email-log/test",
        headers=h,
        json={"to_email": "not-an-email"},
    )
    assert r.status_code == 400


def test_test_email_endpoint_requires_admin(client) -> None:
    c, _SL = client
    r = c.post(
        "/api/v1/admin/email-log/test",
        json={"to_email": "anyone@example.com"},
    )
    assert r.status_code == 401
