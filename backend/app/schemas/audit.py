"""Audit log schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class AuditLogListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
    actor_id: int | None
    actor_email: str
    actor_role: str
    ip_address: str
    action: str
    entity_type: str
    entity_id: int | None
    summary: str


class AuditLogDetail(AuditLogListItem):
    user_agent: str
    before: dict[str, Any]
    after: dict[str, Any]
    meta: dict[str, Any]
    prev_hash: str
    row_hash: str


class VerifyResult(BaseModel):
    verified: bool
    count: int
    issues: list[dict[str, Any]]
    checked_at: str
