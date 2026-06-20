"""Phase 17: user-options dropdown filtering + lawyer division M2M."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import *  # noqa: F401,F403
from app.models.masters import Division
from app.models.user import Role, User, UserDivisionMap
from app.services.seed import DEFAULT_ADMIN_EMAIL, DEFAULT_ADMIN_PASSWORD, run_seed


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
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


def _login(client: TestClient) -> dict[str, str]:
    r = client.post(
        "/api/v1/auth/login",
        json={"email": DEFAULT_ADMIN_EMAIL, "password": DEFAULT_ADMIN_PASSWORD},
    )
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _seed_two_divisions_with_managers(SessionLocal) -> tuple[int, int]:
    db = SessionLocal()
    try:
        d1 = Division(code="D1", name="North")
        d2 = Division(code="D2", name="South")
        db.add_all([d1, d2])
        db.flush()
        sm_role = db.query(Role).filter(Role.name == "Sales Manager").first()
        ch_role = db.query(Role).filter(Role.name == "Chairman / MD").first()
        # Sales Manager attached to D1 only
        u1 = User(
            email="sm1@pug.local",
            password_hash=hash_password("Pass@1234"),
            full_name="SM-D1",
            role_id=sm_role.id,
        )
        # Sales Manager attached to D2 only
        u2 = User(
            email="sm2@pug.local",
            password_hash=hash_password("Pass@1234"),
            full_name="SM-D2",
            role_id=sm_role.id,
        )
        # Chairman attached to nothing (cross-division)
        u3 = User(
            email="chair@pug.local",
            password_hash=hash_password("Pass@1234"),
            full_name="Chair-1",
            role_id=ch_role.id,
        )
        db.add_all([u1, u2, u3])
        db.flush()
        db.add(UserDivisionMap(user_id=u1.id, division_id=d1.id))
        db.add(UserDivisionMap(user_id=u2.id, division_id=d2.id))
        db.commit()
        return d1.id, d2.id
    finally:
        db.close()


def test_user_options_filters_sales_manager_by_division(client) -> None:
    c, SessionLocal = client
    d1, d2 = _seed_two_divisions_with_managers(SessionLocal)
    h = _login(c)

    # No division filter -> both SMs returned
    rows = c.get("/api/v1/users/options?role=Sales+Manager", headers=h).json()
    names = sorted(r["full_name"] for r in rows)
    assert names == ["SM-D1", "SM-D2"]

    # Filter by division D1 -> only SM-D1
    rows = c.get(
        f"/api/v1/users/options?role=Sales+Manager&division_id={d1}",
        headers=h,
    ).json()
    assert [r["full_name"] for r in rows] == ["SM-D1"]

    # Filter by division D2 -> only SM-D2
    rows = c.get(
        f"/api/v1/users/options?role=Sales+Manager&division_id={d2}",
        headers=h,
    ).json()
    assert [r["full_name"] for r in rows] == ["SM-D2"]


def test_user_options_ignores_division_filter_for_chairman(client) -> None:
    c, SessionLocal = client
    d1, _d2 = _seed_two_divisions_with_managers(SessionLocal)
    h = _login(c)

    # Chairman / MD is a cross-division role; the division filter
    # must NOT exclude them even though they aren't mapped to D1.
    rows = c.get(
        f"/api/v1/users/options?role=Chairman+%2F+MD&division_id={d1}",
        headers=h,
    ).json()
    assert any(r["full_name"] == "Chair-1" for r in rows)


def test_lawyer_division_round_trip(client) -> None:
    c, _ = client
    h = _login(c)
    divs = c.get("/api/v1/masters/divisions", headers=h).json()
    assert len(divs) >= 1
    d_id = divs[0]["id"]

    # Create a lawyer with one explicit division
    r = c.post(
        "/api/v1/masters/lawyers",
        headers=h,
        json={
            "name": "John Doe",
            "firm": "Doe & Co",
            "is_all_divisions": False,
            "division_ids": [d_id],
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["is_all_divisions"] is False
    assert body["division_ids"] == [d_id]
    lawyer_id = body["id"]

    # Flip to All Companies -> division_ids should be cleared on the server
    r = c.patch(
        f"/api/v1/masters/lawyers/{lawyer_id}",
        headers=h,
        json={"is_all_divisions": True},
    )
    assert r.status_code == 200
    assert r.json()["is_all_divisions"] is True
    assert r.json()["division_ids"] == []

    # And back to one division
    r = c.patch(
        f"/api/v1/masters/lawyers/{lawyer_id}",
        headers=h,
        json={"is_all_divisions": False, "division_ids": [d_id]},
    )
    assert r.status_code == 200
    assert r.json()["is_all_divisions"] is False
    assert r.json()["division_ids"] == [d_id]


def test_user_options_requires_auth(client) -> None:
    c, _ = client
    assert c.get("/api/v1/users/options").status_code == 401
