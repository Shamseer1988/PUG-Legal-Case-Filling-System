"""Phase 7: scheduled reports + run history.

Revision ID: 0006_phase7_scheduled_reports
Revises: 0005_phase5_notifications
Create Date: 2026-06-19
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_phase7_scheduled_reports"
down_revision: str | None = "0005_phase5_notifications"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _ts() -> list[sa.Column]:
    return [
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
    ]


def upgrade() -> None:
    op.create_table(
        "scheduled_reports",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("report_key", sa.String(50), nullable=False),
        sa.Column("params", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("cron", sa.String(50), nullable=False),
        sa.Column("timezone", sa.String(50), nullable=False, server_default="UTC"),
        sa.Column("recipients", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("cc", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("bcc", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("formats", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("notes", sa.String(500), nullable=False, server_default=""),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_status", sa.String(20), nullable=False, server_default=""),
        sa.Column("last_run_error", sa.Text, nullable=False, server_default=""),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_by_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        *_ts(),
    )
    op.create_index("ix_scheduled_reports_report_key", "scheduled_reports", ["report_key"])
    op.create_index("ix_scheduled_reports_is_active", "scheduled_reports", ["is_active"])

    op.create_table(
        "scheduled_report_runs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "schedule_id",
            sa.Integer,
            sa.ForeignKey("scheduled_reports.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("rows_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error", sa.Text, nullable=False, server_default=""),
        sa.Column(
            "email_log_id",
            sa.Integer,
            sa.ForeignKey("email_log.id", ondelete="SET NULL"),
            nullable=True,
        ),
        *_ts(),
    )
    op.create_index(
        "ix_scheduled_report_runs_schedule_id", "scheduled_report_runs", ["schedule_id"]
    )
    op.create_index("ix_scheduled_report_runs_status", "scheduled_report_runs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_scheduled_report_runs_status", table_name="scheduled_report_runs")
    op.drop_index(
        "ix_scheduled_report_runs_schedule_id", table_name="scheduled_report_runs"
    )
    op.drop_table("scheduled_report_runs")
    op.drop_index("ix_scheduled_reports_is_active", table_name="scheduled_reports")
    op.drop_index("ix_scheduled_reports_report_key", table_name="scheduled_reports")
    op.drop_table("scheduled_reports")
