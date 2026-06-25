"""Phase 44: Accountant division-scoped create for Customers and Salesmen."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.permissions import MASTERS_CREATE_OWN_DIVISION, ROLE_PRESETS
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
    db_path = tmp_path / "phase44.db"
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


def _login(c: TestClient, email: str, password: str = "Pass@1234") -> str:
    r = c.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _setup_divisions_and_accountant(SessionLocal):
    """Create two Divisions and one Accountant user scoped to the first."""
    db = SessionLocal()
    try:
        div_a = Division(code="44A", name="Div A")
        div_b = Division(code="44B", name="Div B")
        db.add_all([div_a, div_b])
        db.flush()

        role = db.query(Role).filter(Role.name == "Accountant").first()
        user = User(
            email="acct44@pug.local",
            password_hash=hash_password("Pass@1234"),
            full_name="Accountant44",
            role_id=role.id,
            is_active=True,
            is_super=False,
        )
        db.add(user)
        db.flush()
        db.add(UserDivisionMap(user_id=user.id, division_id=div_a.id))
        db.commit()
        return div_a.id, div_b.id
    finally:
        db.close()


# ---- pure-Python test (no DB) ----

def test_accountant_preset_includes_create_own_division():
    """Seed preset for Accountant must carry the new permission."""
    assert MASTERS_CREATE_OWN_DIVISION in ROLE_PRESETS["Accountant"]


# ---- API integration tests ----

def test_accountant_can_create_customer_in_own_division(client):
    c, SL = client
    div_a_id, _ = _setup_divisions_and_accountant(SL)
    token = _login(c, "acct44@pug.local")
    r = c.post(
        "/api/v1/masters/customers",
        json={"code": "C44A", "name": "Cust A", "division_id": div_a_id, "is_active": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["division_id"] == div_a_id


def test_accountant_blocked_from_other_division(client):
    c, SL = client
    div_a_id, div_b_id = _setup_divisions_and_accountant(SL)
    token = _login(c, "acct44@pug.local")
    r = c.post(
        "/api/v1/masters/customers",
        json={"code": "C44B", "name": "Cust B", "division_id": div_b_id, "is_active": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403, r.text


def test_accountant_can_create_salesman_in_own_division(client):
    c, SL = client
    div_a_id, _ = _setup_divisions_and_accountant(SL)
    token = _login(c, "acct44@pug.local")
    r = c.post(
        "/api/v1/masters/salesmen",
        json={"code": "SM44A", "name": "SM A", "division_id": div_a_id, "is_active": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 201, r.text


def test_accountant_cannot_create_salesman_in_other_division(client):
    c, SL = client
    div_a_id, div_b_id = _setup_divisions_and_accountant(SL)
    token = _login(c, "acct44@pug.local")
    r = c.post(
        "/api/v1/masters/salesmen",
        json={"code": "SM44B", "name": "SM B", "division_id": div_b_id, "is_active": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403, r.text


def test_accountant_cannot_update_customer(client):
    """Accountant lacks masters:write — PATCH must return 403."""
    c, SL = client
    div_a_id, _ = _setup_divisions_and_accountant(SL)

    # Create as admin
    admin_token = _login(c, DEFAULT_ADMIN_EMAIL, DEFAULT_ADMIN_PASSWORD)
    r = c.post(
        "/api/v1/masters/customers",
        json={"code": "C44UPD", "name": "Updatable", "division_id": div_a_id, "is_active": True},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 201
    cust_id = r.json()["id"]

    acct_token = _login(c, "acct44@pug.local")
    r2 = c.patch(
        f"/api/v1/masters/customers/{cust_id}",
        json={"name": "Renamed"},
        headers={"Authorization": f"Bearer {acct_token}"},
    )
    assert r2.status_code == 403, r2.text


def test_accountant_cannot_delete_customer(client):
    c, SL = client
    div_a_id, _ = _setup_divisions_and_accountant(SL)

    admin_token = _login(c, DEFAULT_ADMIN_EMAIL, DEFAULT_ADMIN_PASSWORD)
    r = c.post(
        "/api/v1/masters/customers",
        json={"code": "C44DEL", "name": "Deletable", "division_id": div_a_id, "is_active": True},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 201
    cust_id = r.json()["id"]

    acct_token = _login(c, "acct44@pug.local")
    r2 = c.delete(
        f"/api/v1/masters/customers/{cust_id}",
        headers={"Authorization": f"Bearer {acct_token}"},
    )
    assert r2.status_code == 403, r2.text
