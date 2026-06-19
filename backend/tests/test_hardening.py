"""Phase 12 tests: security headers, rate limit, 2FA enrolment/login."""

import pyotp
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
    monkeypatch.setenv("RATE_LIMIT_LOGIN_PER_MINUTE", "3")
    monkeypatch.setenv("RATE_LIMIT_LOGIN_PER_HOUR", "100")
    (tmp_path / "storage").mkdir()
    (tmp_path / "backups").mkdir()

    # Clear cached settings so env overrides apply
    from app.core import config

    config.get_settings.cache_clear()
    # Reset in-memory rate-limit buckets between tests
    from app.core.hardening import _limiter

    _limiter._buckets.clear()

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


def _login(client: TestClient, **extra) -> dict:
    payload = {
        "email": DEFAULT_ADMIN_EMAIL,
        "password": DEFAULT_ADMIN_PASSWORD,
        **extra,
    }
    return client.post("/api/v1/auth/login", json=payload)


def test_security_headers_present(client: TestClient) -> None:
    r = client.get("/")
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    assert r.headers.get("X-Frame-Options") == "DENY"
    assert "Referrer-Policy" in r.headers


def test_rate_limit_on_login(client: TestClient) -> None:
    # 3-per-minute config; the 4th attempt with bad creds should 429
    for i in range(3):
        r = client.post(
            "/api/v1/auth/login",
            json={"email": DEFAULT_ADMIN_EMAIL, "password": "wrong"},
        )
        assert r.status_code == 401
    r = client.post(
        "/api/v1/auth/login",
        json={"email": DEFAULT_ADMIN_EMAIL, "password": "wrong"},
    )
    assert r.status_code == 429


def test_2fa_enroll_and_login(client: TestClient) -> None:
    r = _login(client)
    assert r.status_code == 200, r.text
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    # Enrol
    enroll = client.post("/api/v1/auth/2fa/enroll", headers=headers).json()
    assert enroll["secret"]
    assert enroll["qr_data_url"].startswith("data:image/png;base64,")

    # Activate with a fresh TOTP code
    code = pyotp.TOTP(enroll["secret"]).now()
    r = client.post("/api/v1/auth/2fa/verify", headers=headers, json={"code": code})
    assert r.status_code == 200, r.text
    assert r.json()["enabled"] is True

    # Confirm /me reflects it
    me = client.get("/api/v1/auth/me", headers=headers).json()
    assert me["totp_enabled"] is True

    # Login without code -> 401 totp_required
    r = _login(client)
    assert r.status_code == 401
    assert r.json()["detail"] == "totp_required"

    # Login with code -> success
    r = _login(client, totp_code=pyotp.TOTP(enroll["secret"]).now())
    assert r.status_code == 200, r.text


def test_2fa_disable(client: TestClient) -> None:
    r = _login(client)
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    enroll = client.post("/api/v1/auth/2fa/enroll", headers=headers).json()
    client.post(
        "/api/v1/auth/2fa/verify",
        headers=headers,
        json={"code": pyotp.TOTP(enroll["secret"]).now()},
    )
    # Disable
    r = client.post("/api/v1/auth/2fa/disable", headers=headers)
    assert r.status_code == 200
    me = client.get("/api/v1/auth/me", headers=headers).json()
    assert me["totp_enabled"] is False
