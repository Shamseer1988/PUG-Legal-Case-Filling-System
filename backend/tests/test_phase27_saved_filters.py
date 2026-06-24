"""Phase 27: saved report filter CRUD + visibility rules + inactive
recipient pruning on scheduled-report send."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import *  # noqa: F401,F403
from app.models.user import Role, User
from app.services.seed import DEFAULT_ADMIN_EMAIL, DEFAULT_ADMIN_PASSWORD, run_seed


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "p27.db"
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


def _admin_h(c: TestClient) -> dict[str, str]:
    r = c.post(
        "/api/v1/auth/login",
        json={"email": DEFAULT_ADMIN_EMAIL, "password": DEFAULT_ADMIN_PASSWORD},
    )
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _make_user(SessionLocal, email: str, role_name: str) -> int:
    db = SessionLocal()
    try:
        role = db.query(Role).filter(Role.name == role_name).first()
        u = User(
            email=email,
            password_hash=hash_password("Pass@1234"),
            full_name=role_name,
            role_id=role.id,
        )
        db.add(u)
        db.commit()
        return u.id
    finally:
        db.close()


def _login(c: TestClient, email: str) -> dict[str, str]:
    r = c.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Pass@1234"},
    )
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# ----------------------- CRUD -----------------------
def test_create_list_round_trip(client) -> None:
    c, _ = client
    h = _admin_h(c)
    r = c.post(
        "/api/v1/reports/saved",
        headers=h,
        json={
            "name": "Q2 Civil",
            "report_key": "case_register",
            "params": {"status": "Approved"},
            "is_public": False,
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["is_mine"] is True
    assert body["params"] == {"status": "Approved"}

    rows = c.get("/api/v1/reports/saved", headers=h).json()
    assert any(r["id"] == body["id"] for r in rows)


def test_list_filters_by_report_key(client) -> None:
    c, _ = client
    h = _admin_h(c)
    c.post(
        "/api/v1/reports/saved",
        headers=h,
        json={"name": "A", "report_key": "case_register", "params": {}, "is_public": False},
    )
    c.post(
        "/api/v1/reports/saved",
        headers=h,
        json={"name": "B", "report_key": "status_summary", "params": {}, "is_public": False},
    )
    rows = c.get("/api/v1/reports/saved?report_key=case_register", headers=h).json()
    assert [r["name"] for r in rows] == ["A"]


def test_unknown_report_key_rejected_on_create(client) -> None:
    c, _ = client
    h = _admin_h(c)
    r = c.post(
        "/api/v1/reports/saved",
        headers=h,
        json={"name": "x", "report_key": "ghost", "params": {}, "is_public": False},
    )
    assert r.status_code == 400


# ----------------------- visibility -----------------------
def test_private_filter_invisible_to_other_user(client) -> None:
    c, SessionLocal = client
    admin = _admin_h(c)
    fid = c.post(
        "/api/v1/reports/saved",
        headers=admin,
        json={
            "name": "secret",
            "report_key": "case_register",
            "params": {},
            "is_public": False,
        },
    ).json()["id"]

    _make_user(SessionLocal, "audit@pug.local", "Auditor")
    other = _login(c, "audit@pug.local")
    rows = c.get("/api/v1/reports/saved", headers=other).json()
    assert all(r["id"] != fid for r in rows)
    # Direct fetch must 404 (don't leak the existence of private rows)
    assert c.get(f"/api/v1/reports/saved/{fid}", headers=other).status_code == 404


def test_public_filter_visible_to_other_user_but_not_editable(client) -> None:
    c, SessionLocal = client
    admin = _admin_h(c)
    fid = c.post(
        "/api/v1/reports/saved",
        headers=admin,
        json={
            "name": "team filter",
            "report_key": "case_register",
            "params": {},
            "is_public": True,
        },
    ).json()["id"]

    _make_user(SessionLocal, "audit2@pug.local", "Auditor")
    other = _login(c, "audit2@pug.local")
    # Visible in list + by-id
    rows = c.get("/api/v1/reports/saved", headers=other).json()
    assert any(r["id"] == fid for r in rows)
    body = c.get(f"/api/v1/reports/saved/{fid}", headers=other).json()
    assert body["is_mine"] is False

    # ... but cannot patch or delete it
    assert c.patch(
        f"/api/v1/reports/saved/{fid}",
        headers=other,
        json={"name": "tampered"},
    ).status_code == 403
    assert c.delete(f"/api/v1/reports/saved/{fid}", headers=other).status_code == 403


def test_owner_can_update_and_delete(client) -> None:
    c, _ = client
    h = _admin_h(c)
    fid = c.post(
        "/api/v1/reports/saved",
        headers=h,
        json={
            "name": "original",
            "report_key": "case_register",
            "params": {},
            "is_public": False,
        },
    ).json()["id"]
    r = c.patch(
        f"/api/v1/reports/saved/{fid}",
        headers=h,
        json={"name": "renamed", "params": {"status": "Filed"}, "is_public": True},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "renamed"
    assert body["params"] == {"status": "Filed"}
    assert body["is_public"] is True

    assert c.delete(f"/api/v1/reports/saved/{fid}", headers=h).status_code == 204
    assert c.get(f"/api/v1/reports/saved/{fid}", headers=h).status_code == 404


def test_saved_filter_endpoints_require_auth(client) -> None:
    c, _ = client
    assert c.get("/api/v1/reports/saved").status_code == 401
    assert c.post(
        "/api/v1/reports/saved",
        json={"name": "x", "report_key": "case_register", "params": {}, "is_public": False},
    ).status_code == 401


# ----------------------- inactive recipient pruning -----------------------
def test_inactive_recipients_dropped_at_send_time(client) -> None:
    """A user whose account was deactivated should silently fall
    off the scheduled-report recipient list at send time."""
    c, SessionLocal = client
    h = _admin_h(c)
    # Seed an active + an inactive user
    active = _make_user(SessionLocal, "active@pug.local", "Auditor")
    inactive = _make_user(SessionLocal, "inactive@pug.local", "Auditor")
    db = SessionLocal()
    try:
        u = db.get(User, inactive)
        u.is_active = False
        db.commit()
    finally:
        db.close()

    from app.services.scheduled_reports import _filter_active_recipients

    db = SessionLocal()
    try:
        out = _filter_active_recipients(
            db,
            [
                "active@pug.local",
                "inactive@pug.local",
                "external@nowhere.example.com",
            ],
        )
        # Active user kept, inactive dropped, unknown external kept.
        assert "active@pug.local" in out
        assert "external@nowhere.example.com" in out
        assert "inactive@pug.local" not in out
    finally:
        db.close()
