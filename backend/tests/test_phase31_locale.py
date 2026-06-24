"""Phase 31: per-user locale preference + per-locale email templates."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import *  # noqa: F401,F403
from app.models.notification import EmailLog
from app.models.user import User
from app.services.seed import DEFAULT_ADMIN_EMAIL, DEFAULT_ADMIN_PASSWORD, run_seed


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "p31.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
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


def test_me_returns_default_locale_en(client) -> None:
    c, _ = client
    h = _admin_h(c)
    body = c.get("/api/v1/auth/me", headers=h).json()
    assert body["locale"] == "en"


def test_locale_round_trip(client) -> None:
    c, SessionLocal = client
    h = _admin_h(c)
    r = c.post("/api/v1/auth/me/locale", headers=h, json={"locale": "ar"})
    assert r.status_code == 200, r.text
    assert r.json()["locale"] == "ar"

    # /me reflects it across logins (persisted to DB)
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.email == DEFAULT_ADMIN_EMAIL).first()
        assert u.locale == "ar"
    finally:
        db.close()

    # Switching back to en works
    r = c.post("/api/v1/auth/me/locale", headers=h, json={"locale": "en"})
    assert r.status_code == 200
    assert r.json()["locale"] == "en"


def test_locale_rejects_unknown_value(client) -> None:
    c, _ = client
    h = _admin_h(c)
    r = c.post("/api/v1/auth/me/locale", headers=h, json={"locale": "fr"})
    assert r.status_code == 422  # Pydantic regex rejects


def test_locale_endpoint_requires_auth(client) -> None:
    c, _ = client
    assert c.post(
        "/api/v1/auth/me/locale", json={"locale": "ar"}
    ).status_code == 401


def test_notification_picks_arabic_template_for_ar_user(client) -> None:
    """Trigger a workflow notification while the user is set to ``ar``
    and assert the EmailLog row was rendered from the AR template."""
    c, SessionLocal = client
    h = _admin_h(c)
    c.post("/api/v1/auth/me/locale", headers=h, json={"locale": "ar"})

    # Create + submit a case so on_case_submitted fires. The seeded
    # admin is the only signatory candidate; we just need *some*
    # notification email to land in the log so we can inspect it.
    divs = c.get("/api/v1/masters/divisions", headers=h).json()
    div_id = divs[0]["id"]
    banks = c.get("/api/v1/masters/banks", headers=h).json()
    cust = c.post(
        "/api/v1/masters/customers",
        headers=h,
        json={"code": "AR1", "name": "AR Co", "division_id": div_id},
    ).json()
    # Set the admin as the Sales Manager signatory so they receive
    # the notification (and we can check their locale picked the
    # AR template).
    me = c.get("/api/v1/auth/me", headers=h).json()
    case_id = c.post(
        "/api/v1/cases",
        headers=h,
        json={
            "customer_id": cust["id"],
            "division_id": div_id,
            "is_civil": True,
            "sales_manager_id": me["id"],
            "cheques": [
                {
                    "cheque_number": "CH-AR-1",
                    "bank_id": banks[0]["id"],
                    "amount": "1000.00",
                    "cheque_date": "2026-05-15",
                    "cheque_type": "Normal",
                    "bounce_reason": "Funds",
                },
            ],
        },
    ).json()["id"]
    c.post(f"/api/v1/cases/{case_id}/submit", headers=h)

    db = SessionLocal()
    try:
        rows = db.query(EmailLog).order_by(EmailLog.id.desc()).all()
        assert rows, "expected at least one EmailLog entry"
        sent = next(
            (r for r in rows if r.template_name == "notification_email.ar.html"),
            None,
        )
        assert sent is not None, (
            "expected at least one row using the AR template; got templates: "
            f"{[r.template_name for r in rows]}"
        )
        # Body should actually contain Arabic, not the English wrapper
        assert "نظام إدارة القضايا القانونية" in sent.body_html
    finally:
        db.close()


def test_notification_uses_english_template_for_en_user(client) -> None:
    c, SessionLocal = client
    h = _admin_h(c)
    # Default locale is en; trigger a notification the same way.
    divs = c.get("/api/v1/masters/divisions", headers=h).json()
    div_id = divs[0]["id"]
    banks = c.get("/api/v1/masters/banks", headers=h).json()
    cust = c.post(
        "/api/v1/masters/customers",
        headers=h,
        json={"code": "EN1", "name": "EN Co", "division_id": div_id},
    ).json()
    me = c.get("/api/v1/auth/me", headers=h).json()
    case_id = c.post(
        "/api/v1/cases",
        headers=h,
        json={
            "customer_id": cust["id"],
            "division_id": div_id,
            "is_civil": True,
            "sales_manager_id": me["id"],
            "cheques": [
                {
                    "cheque_number": "CH-EN-1",
                    "bank_id": banks[0]["id"],
                    "amount": "1000.00",
                    "cheque_date": "2026-05-15",
                    "cheque_type": "Normal",
                    "bounce_reason": "Funds",
                },
            ],
        },
    ).json()["id"]
    c.post(f"/api/v1/cases/{case_id}/submit", headers=h)

    db = SessionLocal()
    try:
        rows = db.query(EmailLog).order_by(EmailLog.id.desc()).limit(5).all()
        used = {r.template_name for r in rows}
        assert "notification_email.html" in used
        assert "notification_email.ar.html" not in used
    finally:
        db.close()
