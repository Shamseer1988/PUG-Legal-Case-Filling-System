"""Approval workflow schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TransitionRequest(BaseModel):
    action: str = Field(pattern="^(approve|reject|request_clarification|resubmit|comment)$")
    comment: str = ""
    # IDs of pre-uploaded CaseTransitionAttachment rows to bind into
    # the new CaseStatusUpdate row created by this transition.
    attachment_ids: list[int] = Field(default_factory=list)


class TransitionAttachmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    case_id: int
    transition_id: int | None
    original_filename: str
    mime_type: str
    size_bytes: int
    uploaded_by_id: int
    uploaded_by_name: str = ""
    created_at: datetime


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
    attachments: list[TransitionAttachmentRead] = Field(default_factory=list)


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
