"""Approval workflow configuration: stages, ordering, SLAs, permissions.

This is the canonical source of truth for the multi-stage case lifecycle:

    Draft (Accountant)
      |  Submit
      v
    Sales Manager  ->  Division Manager  ->  Audit  ->
      Finance Manager  ->  Executive Director  ->  Chairman / MD
      |  (final approve)
      v
    Lawyer  (court filing happens in Phase 4)

At any stage:
- Approve         -> advance to next stage
- Reject          -> status=Rejected (terminal, stage unchanged for record)
- Request Clarify -> stage=Accountant, status=Clarification Requested
- Resubmit (acct) -> back to the stage that asked for clarification
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StageConfig:
    key: str
    stage: str
    permission: str
    user_field: str | None
    next_stage: str | None
    sla_hours: int
    is_final_approval: bool = False


WORKFLOW_STAGES: list[StageConfig] = [
    StageConfig(
        key="sales_mgr",
        stage="Sales Manager",
        permission="cases:approve:sales_mgr",
        user_field="sales_manager_id",
        next_stage="Division Manager",
        sla_hours=24,
    ),
    StageConfig(
        key="div_mgr",
        stage="Division Manager",
        permission="cases:approve:div_mgr",
        user_field="division_manager_id",
        next_stage="Audit",
        sla_hours=24,
    ),
    StageConfig(
        key="audit",
        stage="Audit",
        permission="cases:approve:audit",
        user_field="auditor_id",
        next_stage="Finance Manager",
        sla_hours=48,
    ),
    StageConfig(
        key="fm",
        stage="Finance Manager",
        permission="cases:approve:fm",
        user_field="fm_id",
        next_stage="Executive Director",
        sla_hours=24,
    ),
    StageConfig(
        key="ed",
        stage="Executive Director",
        permission="cases:approve:ed",
        user_field="ed_id",
        next_stage="Chairman / MD",
        sla_hours=48,
    ),
    StageConfig(
        key="chairman",
        stage="Chairman / MD",
        permission="cases:approve:final",
        user_field="chairman_id",
        next_stage="Lawyer",
        sla_hours=72,
        is_final_approval=True,
    ),
]


STAGE_BY_NAME: dict[str, StageConfig] = {s.stage: s for s in WORKFLOW_STAGES}
APPROVAL_STAGE_ORDER: list[str] = [s.stage for s in WORKFLOW_STAGES]


def get_stage(name: str) -> StageConfig | None:
    return STAGE_BY_NAME.get(name)


def is_approval_stage(name: str) -> bool:
    return name in STAGE_BY_NAME


def stage_index(name: str) -> int:
    try:
        return APPROVAL_STAGE_ORDER.index(name)
    except ValueError:
        return -1
