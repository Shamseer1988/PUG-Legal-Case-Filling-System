"""Phase 22: case typeahead search + dashboard drafts exclusion."""

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
    db_path = tmp_path / "p22.db"
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


def _seed_cases(c: TestClient, h: dict[str, str]) -> dict[str, int]:
    divs = c.get("/api/v1/masters/divisions", headers=h).json()
    div_id = divs[0]["id"]
    banks = c.get("/api/v1/masters/banks", headers=h).json()
    out: dict[str, int] = {}
    # Two distinct customers so search-by-customer can verify scoping
    for code, name in (("CT22A", "Alpha Industries"), ("CT22B", "Beta Trading")):
        cust = c.post(
            "/api/v1/masters/customers",
            headers=h,
            json={"code": code, "name": name, "division_id": div_id},
        ).json()
        case_id = c.post(
            "/api/v1/cases",
            headers=h,
            json={
                "customer_id": cust["id"],
                "division_id": div_id,
                "is_civil": True,
                "legal_filing_amount": "1500.00",
                "cheques": [
                    {
                        "cheque_number": f"CH-22-{code}",
                        "bank_id": banks[0]["id"],
                        "amount": "1500.00",
                        "cheque_date": "2026-05-15",
                        "cheque_type": "Normal",
                        "bounce_reason": "Funds",
                    },
                ],
            },
        ).json()["id"]
        out[name] = case_id
    return out


def test_search_returns_typeahead_metadata(client: TestClient) -> None:
    h = _admin_h(client)
    cases = _seed_cases(client, h)
    rows = client.get("/api/v1/cases/search", headers=h).json()
    assert len(rows) == 2
    by_id = {r["id"]: r for r in rows}
    for name, case_id in cases.items():
        hit = by_id[case_id]
        assert hit["customer_name"] == name
        assert hit["case_no"].startswith("PUG-LEGAL-")
        assert hit["legal_filing_amount"] == "1500.00"
        assert hit["division_name"]
        assert hit["status"] == "Draft"


def test_search_filters_by_customer_name(client: TestClient) -> None:
    h = _admin_h(client)
    _seed_cases(client, h)
    rows = client.get("/api/v1/cases/search?q=beta", headers=h).json()
    assert len(rows) == 1
    assert rows[0]["customer_name"] == "Beta Trading"


def test_search_filters_by_case_no_prefix(client: TestClient) -> None:
    h = _admin_h(client)
    _seed_cases(client, h)
    # The case_no format is PUG-LEGAL-YYYY-NNNN; anything matching the
    # PUG prefix should come back.
    rows = client.get("/api/v1/cases/search?q=PUG-LEGAL", headers=h).json()
    assert len(rows) == 2


def test_search_respects_limit(client: TestClient) -> None:
    h = _admin_h(client)
    _seed_cases(client, h)
    rows = client.get("/api/v1/cases/search?limit=1", headers=h).json()
    assert len(rows) == 1


def test_search_requires_auth(client: TestClient) -> None:
    assert client.get("/api/v1/cases/search").status_code == 401


def test_kpis_total_legal_amount_excludes_drafts(client: TestClient) -> None:
    h = _admin_h(client)
    cases = _seed_cases(client, h)
    # Before submit: all 2 cases are Draft -> total_legal_amount excludes them
    kpis = client.get("/api/v1/dashboard/kpis", headers=h).json()
    assert kpis["total_cases"] == 2
    assert kpis["total_legal_amount"] == "0"

    # Submit one -> only the submitted case contributes
    target = next(iter(cases.values()))
    client.post(f"/api/v1/cases/{target}/submit", headers=h)
    kpis = client.get("/api/v1/dashboard/kpis", headers=h).json()
    assert kpis["total_legal_amount"] == "1500.00"


def test_cash_flow_param_uses_case_search_type(client: TestClient) -> None:
    """The reports list descriptor exposes the new typeahead-friendly
    param type so the frontend knows to render the case combobox."""
    h = _admin_h(client)
    reports = client.get("/api/v1/reports", headers=h).json()
    flow = next(r for r in reports if r["key"] == "case_cash_flow")
    case_param = next(p for p in flow["params"] if p["name"] == "case_no")
    assert case_param["type"] == "case_search"
