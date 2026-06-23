"""Phase 37: User.is_all_divisions ("All Companies") flag."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import *  # noqa: F401,F403
from app.models.user import User, UserDivisionMap
from app.services.seed import DEFAULT_ADMIN_EMAIL, DEFAULT_ADMIN_PASSWORD, run_seed


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "p37.db"
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


def _create_user(c, h, *, email, role_name, is_all_divisions, division_ids):
    roles = c.get("/api/v1/roles", headers=h).json()
    role_id = next(r["id"] for r in roles if r["name"] == role_name)
    body = {
        "email": email,
        "full_name": email.split("@")[0],
        "password": "Pa55word!",
        "role_id": role_id,
        "is_active": True,
        "is_super": False,
        "is_all_divisions": is_all_divisions,
        "division_ids": division_ids,
    }
    r = c.post("/api/v1/users", headers=h, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_create_user_with_all_divisions_clears_division_ids(client) -> None:
    c, SessionLocal = client
    h = _admin_h(c)
    divs = c.get("/api/v1/masters/divisions", headers=h).json()
    div_ids = [d["id"] for d in divs[:2]]
    body = _create_user(
        c,
        h,
        email="across@example.com",
        role_name="Accountant",
        is_all_divisions=True,
        division_ids=div_ids,  # sent but should be ignored
    )
    assert body["is_all_divisions"] is True
    assert body["division_ids"] == []

    # And no mapping rows landed in the DB.
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.email == "across@example.com").first()
        assert u is not None
        n = (
            db.query(UserDivisionMap)
            .filter(UserDivisionMap.user_id == u.id)
            .count()
        )
        assert n == 0
    finally:
        db.close()


def test_patch_flipping_all_divisions_on_wipes_mappings(client) -> None:
    c, SessionLocal = client
    h = _admin_h(c)
    divs = c.get("/api/v1/masters/divisions", headers=h).json()
    div_ids = [d["id"] for d in divs[:2]]

    created = _create_user(
        c,
        h,
        email="scoped@example.com",
        role_name="Sales Manager",
        is_all_divisions=False,
        division_ids=div_ids,
    )
    assert sorted(created["division_ids"]) == sorted(div_ids)

    # Now flip the flag on without sending division_ids.
    r = c.patch(
        f"/api/v1/users/{created['id']}",
        headers=h,
        json={"is_all_divisions": True},
    )
    assert r.status_code == 200, r.text
    after = r.json()
    assert after["is_all_divisions"] is True
    assert after["division_ids"] == []

    db = SessionLocal()
    try:
        n = (
            db.query(UserDivisionMap)
            .filter(UserDivisionMap.user_id == created["id"])
            .count()
        )
        assert n == 0
    finally:
        db.close()


def test_user_options_picker_returns_all_divisions_user_for_any_division(
    client,
) -> None:
    """An ``is_all_divisions=True`` Sales Manager shows up on every
    division's signatory picker."""
    c, _ = client
    h = _admin_h(c)
    divs = c.get("/api/v1/masters/divisions", headers=h).json()
    _create_user(
        c,
        h,
        email="anysm@example.com",
        role_name="Sales Manager",
        is_all_divisions=True,
        division_ids=[],
    )
    for d in divs:
        rows = c.get(
            f"/api/v1/users/options?role=Sales Manager&division_id={d['id']}",
            headers=h,
        ).json()
        assert any(r["email"] == "anysm@example.com" for r in rows), (
            f"All-Companies SM missing from picker for division {d['id']}"
        )


def test_scoped_query_lets_all_divisions_user_see_every_case(client) -> None:
    """A non-super Accountant marked ``is_all_divisions`` should
    see cases that landed in any division."""
    c, _ = client
    h = _admin_h(c)
    divs = c.get("/api/v1/masters/divisions", headers=h).json()
    banks = c.get("/api/v1/masters/banks", headers=h).json()
    bank_id = banks[0]["id"]

    # Make one case in each of the first two divisions (using the
    # admin's session, since the seed admin can create cases).
    case_ids = []
    for idx, d in enumerate(divs[:2]):
        cust = c.post(
            "/api/v1/masters/customers",
            headers=h,
            json={"code": f"P37C{idx}", "name": f"P37 cust {idx}", "division_id": d["id"]},
        ).json()
        case = c.post(
            "/api/v1/cases",
            headers=h,
            json={
                "customer_id": cust["id"],
                "division_id": d["id"],
                "is_civil": True,
                "cheques": [
                    {
                        "cheque_number": f"P37-{idx}",
                        "bank_id": bank_id,
                        "amount": "1.00",
                        "cheque_date": "2026-05-15",
                        "cheque_type": "Normal",
                        "bounce_reason": "x",
                    }
                ],
            },
        ).json()
        case_ids.append(case["id"])

    # Now register a new Accountant with All Companies and log in.
    _create_user(
        c,
        h,
        email="reader@example.com",
        role_name="Accountant",
        is_all_divisions=True,
        division_ids=[],
    )
    r = c.post(
        "/api/v1/auth/login",
        json={"email": "reader@example.com", "password": "Pa55word!"},
    )
    hh = {"Authorization": f"Bearer {r.json()['access_token']}"}
    rows = c.get("/api/v1/cases", headers=hh).json()
    visible_ids = {row["id"] for row in rows}
    # Both cases (from different divisions) must be visible.
    assert set(case_ids).issubset(visible_ids), (
        f"All-Companies reader missed cases: {set(case_ids) - visible_ids}"
    )


def test_default_user_is_not_all_divisions(client) -> None:
    """Existing rows + freshly created users default to False."""
    c, _ = client
    h = _admin_h(c)
    rows = c.get("/api/v1/users", headers=h).json()
    # The seeded admin is super, not all-divisions.
    admin = next(r for r in rows if r["email"] == DEFAULT_ADMIN_EMAIL)
    assert admin["is_all_divisions"] is False
