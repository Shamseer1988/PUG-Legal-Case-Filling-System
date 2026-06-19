"""Approval workflow schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TransitionRequest(BaseModel):
    action: str = Field(pattern="^(approve|reject|request_clarification|resubmit|comment)$")
    comment: str = ""


class TimelineEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    action_type: str
    from_status: str
    to_status: str
    from_stage: str
    to_stage: str
    actor_id: int
    actor_name: str = ""
    comment: str
    created_at: datetime


class InboxItem(BaseModel):
    id: int
    case_no: str
    customer_id: int
    division_id: int
    current_stage: str
    status: str
    stage_entered_at: datetime | None
    sla_due_at: datetime | None
    overdue: bool
    legal_filing_amount: str
    assigned_to_me: bool


class StageDescriptor(BaseModel):
    key: str
    stage: str
    permission: str
    user_field: str | None
    next_stage: str | None
    sla_hours: int


class WorkflowDescriptor(BaseModel):
    stages: list[StageDescriptor]
    accountant_stage: str
    lawyer_stage: str
