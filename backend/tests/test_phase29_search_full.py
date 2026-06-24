"""Phase 29: advanced cases search + filter combinations."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import *  # noqa: F401,F403
from .conftest import attach_default_signatory
from app.services.seed import DEFAULT_ADMIN_EMAIL, DEFAULT_ADMIN_PASSWORD, run_seed


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "p29.db"
    storage_dir = tmp_path / "storage"
    storage_dir.mkdir()
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("STORAGE_LOCAL_PATH", str(storage_dir))

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
        yield TestClient(app)
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


def _make_case(
    c: TestClient,
    h: dict[str, str],
    customer_code: str,
    customer_name: str,
    *,
    amount: str = "1000.00",
    commands: str = "",
    is_criminal: bool = False,
    is_civil: bool = True,
) -> int:
    divs = c.get("/api/v1/masters/divisions", headers=h).json()
    div_id = divs[0]["id"]
    banks = c.get("/api/v1/masters/banks", headers=h).json()
    cust = c.post(
        "/api/v1/masters/customers",
        headers=h,
        json={"code": customer_code, "name": customer_name, "division_id": div_id},
    ).json()
    return c.post(
        "/api/v1/cases",
        headers=h,
        json={
            "customer_id": cust["id"],
            "division_id": div_id,
            "is_criminal": is_criminal,
            "is_civil": is_civil,
            "legal_filing_amount": amount,
            "commands": commands,
            "cheques": [
                {
                    "cheque_number": f"CH-{customer_code}",
                    "bank_id": banks[0]["id"],
                    "amount": amount,
                    "cheque_date": "2026-05-15",
                    "cheque_type": "Normal",
                    "bounce_reason": "Funds",
                },
            ],
        },
    ).json()["id"]


def test_search_full_returns_paginated_shape(client) -> None:
    h = _admin_h(client)
    _make_case(client, h, "C1", "Alpha Industries")
    body = client.get("/api/v1/cases/search-full", headers=h).json()
    assert "items" in body and "total" in body and "limit" in body and "offset" in body
    assert isinstance(body["items"], list)
    assert body["total"] >= 1


def test_search_full_filters_by_q_against_multiple_fields(client) -> None:
    h = _admin_h(client)
    a = _make_case(client, h, "ACME", "Alpha Industries", commands="urgent matter")
    b = _make_case(client, h, "BETAX", "Beta Trading", commands="routine")

    # q matches customer name
    r = client.get("/api/v1/cases/search-full?q=Beta", headers=h).json()
    assert [i["id"] for i in r["items"]] == [b]

    # q matches customer code
    r = client.get("/api/v1/cases/search-full?q=ACME", headers=h).json()
    assert [i["id"] for i in r["items"]] == [a]

    # q matches commands free text
    r = client.get("/api/v1/cases/search-full?q=urgent", headers=h).json()
    assert [i["id"] for i in r["items"]] == [a]


def test_search_full_status_filter(client) -> None:
    h = _admin_h(client)
    drafted = _make_case(client, h, "DA", "Draft A")
    submitted = _make_case(client, h, "SB", "Submitted B")
    case = client.get(f"/api/v1/cases/{submitted}", headers=h).json()
    attach_default_signatory(client, h, case)
    client.post(f"/api/v1/cases/{submitted}/submit", headers=h)

    r = client.get("/api/v1/cases/search-full?status_in=Draft", headers=h).json()
    ids = [i["id"] for i in r["items"]]
    assert drafted in ids
    assert submitted not in ids


def test_search_full_amount_range(client) -> None:
    h = _admin_h(client)
    cheap = _make_case(client, h, "CHEAP", "Cheap Co", amount="100.00")
    mid = _make_case(client, h, "MID", "Mid Co", amount="5000.00")
    big = _make_case(client, h, "BIG", "Big Co", amount="100000.00")

    r = client.get(
        "/api/v1/cases/search-full?amount_min=1000&amount_max=50000",
        headers=h,
    ).json()
    ids = [i["id"] for i in r["items"]]
    assert ids == [mid], f"got {ids}"
    assert cheap not in ids
    assert big not in ids


def test_search_full_pagination(client) -> None:
    h = _admin_h(client)
    ids = [_make_case(client, h, f"P{i}", f"Co {i}") for i in range(5)]

    page1 = client.get("/api/v1/cases/search-full?limit=2&offset=0", headers=h).json()
    page2 = client.get("/api/v1/cases/search-full?limit=2&offset=2", headers=h).json()
    page3 = client.get("/api/v1/cases/search-full?limit=2&offset=4", headers=h).json()

    assert page1["total"] == 5
    assert len(page1["items"]) == 2
    assert len(page2["items"]) == 2
    assert len(page3["items"]) == 1

    seen = [i["id"] for i in (page1["items"] + page2["items"] + page3["items"])]
    assert set(seen) == set(ids)


def test_search_full_criminal_civil_filter(client) -> None:
    h = _admin_h(client)
    civ = _make_case(client, h, "CIV", "Civ Co", is_criminal=False, is_civil=True)
    cri = _make_case(client, h, "CRI", "Cri Co", is_criminal=True, is_civil=False)

    r = client.get("/api/v1/cases/search-full?is_criminal=true", headers=h).json()
    ids = [i["id"] for i in r["items"]]
    assert cri in ids
    assert civ not in ids


def test_search_full_requires_auth(client) -> None:
    assert client.get("/api/v1/cases/search-full").status_code == 401


def test_search_full_bad_date_returns_400(client) -> None:
    h = _admin_h(client)
    r = client.get("/api/v1/cases/search-full?date_from=not-a-date", headers=h)
    assert r.status_code == 400
