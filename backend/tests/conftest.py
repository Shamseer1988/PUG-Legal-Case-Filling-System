"""Shared test helpers.

Centralised here so Phase 40's "every submitted case must declare
at least one cheque signatory" rule can be satisfied from any
test file without each file re-implementing the partner setup.
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient


def attach_default_signatory(
    client: TestClient,
    headers: dict[str, str],
    case: int | dict[str, Any],
    *,
    name: str = "Default Signatory",
) -> dict[str, Any]:
    """Phase 40: create a cheque-signatory partner on the case's
    customer and link the partner to the case.

    ``case`` may be either the full case dict (returned by POST/
    GET /api/v1/cases/...) OR a bare case id - the helper fetches
    the case dict in the int case so test fixtures that return
    just an integer keep working.

    Returns the partner dict so callers can assert on it.
    No-op safe: re-calling appends another partner.
    """
    if isinstance(case, int):
        case = client.get(f"/api/v1/cases/{case}", headers=headers).json()
    customer_id = case["customer_id"]
    partner = client.post(
        f"/api/v1/masters/customers/{customer_id}/partners",
        headers=headers,
        json={
            "name": name,
            "is_cheque_signatory": True,
            "is_authorised_signatory": True,
            "residency_status": "inside_country",
        },
    ).json()
    existing = case.get("cheque_signatory_partner_ids") or []
    ids = sorted({*existing, partner["id"]})
    client.patch(
        f"/api/v1/cases/{case['id']}",
        headers=headers,
        json={"cheque_signatory_partner_ids": ids},
    )
    return partner
