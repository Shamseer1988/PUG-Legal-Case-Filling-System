"""Phase 3: workflow timeline + SLA fields.

Revision ID: 0003_phase3_workflow
Revises: 0002_phase2_cases
Create Date: 2026-06-19
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_phase3_workflow"
down_revision: str | None = "0002_phase2_cases"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "cases",
        sa.Column("stage_entered_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "cases",
        sa.Column("sla_due_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "case_status_updates",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "case_id",
            sa.Integer,
            sa.ForeignKey("cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("action_type", sa.String(30), nullable=False),
        sa.Column("from_status", sa.String(40), nullable=False),
        sa.Column("to_status", sa.String(40), nullable=False),
        sa.Column("from_stage", sa.String(40), nullable=False),
        sa.Column("to_stage", sa.String(40), nullable=False),
        sa.Column(
            "actor_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("comment", sa.String(2000), nullable=False, server_default=""),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_case_status_updates_case_id",
        "case_status_updates",
        ["case_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_case_status_updates_case_id", table_name="case_status_updates")
    op.drop_table("case_status_updates")
    op.drop_column("cases", "sla_due_at")
    op.drop_column("cases", "stage_entered_at")
