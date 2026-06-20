"""Role -> capability matrix smoke tests for ``GET /auth/me/capabilities``.

The frontend reads this endpoint to decide which menus and action
buttons to render, so the per-role contract must be locked down.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.permissions import (
    ACTION_CASE_APPROVE_SALES_MGR,
    ACTION_CASE_CLOSE,
    ACTION_CASE_LAWYER_APPROVE,
    MENU_ADMIN_AUDIT_LOG,
    MENU_ADMIN_SETTINGS,
    MENU_CASES,
    MENU_DASHBOARD,
    MENU_MASTERS_CUSTOMERS,
    MENU_MASTERS_DIVISIONS,
    MENU_PROFILE,
    MENU_SCHEDULED_REPORTS,
    SCOPE_ALL,
    SCOPE_OWN_DIVISIONS,
)
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import *  # noqa: F401,F403
from app.models.user import Role, User
from app.services.seed import DEFAULT_ADMIN_EMAIL, DEFAULT_ADMIN_PASSWORD, run_seed


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "caps.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")

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


def _login(client: TestClient, email: str, password: str) -> str:
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _make_user(SessionLocal, email: str, role_name: str) -> None:
    db = SessionLocal()
    try:
        role = db.query(Role).filter(Role.name == role_name).first()
        assert role is not None, f"seed missing role {role_name}"
        db.add(
            User(
                email=email,
                password_hash=hash_password("Pass@1234"),
                full_name=role_name,
                role_id=role.id,
                is_active=True,
                is_super=False,
            )
        )
        db.commit()
    finally:
        db.close()


def test_admin_capabilities_full_access(client) -> None:
    c, _ = client
    token = _login(c, DEFAULT_ADMIN_EMAIL, DEFAULT_ADMIN_PASSWORD)
    r = c.get("/api/v1/auth/me/capabilities", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    body = r.json()
    assert body["is_super"] is True
    assert body["scope"] == SCOPE_ALL
    assert MENU_ADMIN_SETTINGS in body["menus"]
    assert MENU_MASTERS_DIVISIONS in body["menus"]
    assert ACTION_CASE_CLOSE in body["actions"]


def test_accountant_menus_hide_masters_extras_and_scheduled_reports(client) -> None:
    c, SessionLocal = client
    _make_user(SessionLocal, "acct@pug.local", "Accountant")
    token = _login(c, "acct@pug.local", "Pass@1234")
    body = c.get(
        "/api/v1/auth/me/capabilities",
        headers={"Authorization": f"Bearer {token}"},
    ).json()
    assert body["scope"] == SCOPE_OWN_DIVISIONS
    assert MENU_MASTERS_CUSTOMERS in body["menus"]
    # Accountant must NOT see Divisions/Lawyers/Case Types under Masters
    assert MENU_MASTERS_DIVISIONS not in body["menus"]
    assert "masters.lawyers" not in body["menus"]
    assert "masters.case_types" not in body["menus"]
    # No Scheduled Reports for Accountant
    assert MENU_SCHEDULED_REPORTS not in body["menus"]


def test_sales_manager_has_no_master_tab(client) -> None:
    c, SessionLocal = client
    _make_user(SessionLocal, "sm@pug.local", "Sales Manager")
    token = _login(c, "sm@pug.local", "Pass@1234")
    body = c.get(
        "/api/v1/auth/me/capabilities",
        headers={"Authorization": f"Bearer {token}"},
    ).json()
    assert body["scope"] == SCOPE_OWN_DIVISIONS
    assert MENU_CASES in body["menus"]
    assert MENU_DASHBOARD in body["menus"]
    assert MENU_PROFILE in body["menus"]
    # No Masters subitems at all
    assert not any(m.startswith("masters.") for m in body["menus"])
    # Sales mgr action only
    assert ACTION_CASE_APPROVE_SALES_MGR in body["actions"]
    assert ACTION_CASE_CLOSE not in body["actions"]


def test_auditor_sees_audit_log_only_under_admin(client) -> None:
    c, SessionLocal = client
    _make_user(SessionLocal, "audit@pug.local", "Auditor")
    token = _login(c, "audit@pug.local", "Pass@1234")
    body = c.get(
        "/api/v1/auth/me/capabilities",
        headers={"Authorization": f"Bearer {token}"},
    ).json()
    assert body["scope"] == SCOPE_ALL
    assert MENU_ADMIN_AUDIT_LOG in body["menus"]
    # No other admin menus
    assert MENU_ADMIN_SETTINGS not in body["menus"]
    # No Masters tab
    assert not any(m.startswith("masters.") for m in body["menus"])


def test_lawyer_has_lawyer_approve_action(client) -> None:
    c, SessionLocal = client
    _make_user(SessionLocal, "lawyer@pug.local", "Lawyer")
    token = _login(c, "lawyer@pug.local", "Pass@1234")
    body = c.get(
        "/api/v1/auth/me/capabilities",
        headers={"Authorization": f"Bearer {token}"},
    ).json()
    assert ACTION_CASE_LAWYER_APPROVE in body["actions"]


def test_capabilities_requires_auth(client) -> None:
    c, _ = client
    r = c.get("/api/v1/auth/me/capabilities")
    assert r.status_code == 401
