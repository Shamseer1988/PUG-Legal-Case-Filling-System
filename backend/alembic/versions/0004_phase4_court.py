"""Phase 4: court filing, hearings, cash requests.

Revision ID: 0004_phase4_court
Revises: 0003_phase3_workflow
Create Date: 2026-06-19
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_phase4_court"
down_revision: str | None = "0003_phase3_workflow"
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
        "court_filings",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "case_id",
            sa.Integer,
            sa.ForeignKey("cases.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("police_case_no", sa.String(60), nullable=False, server_default=""),
        sa.Column("court_case_no", sa.String(60), nullable=False, server_default=""),
        sa.Column("filed_court", sa.String(200), nullable=False, server_default=""),
        sa.Column("filed_date", sa.Date, nullable=True),
        sa.Column(
            "acknowledgment_attachment_id",
            sa.Integer,
            sa.ForeignKey("case_attachments.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "filed_by_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("notes", sa.String(2000), nullable=False, server_default=""),
        *_ts(),
    )

    op.create_table(
        "hearings",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "case_id",
            sa.Integer,
            sa.ForeignKey("cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("hearing_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("location", sa.String(300), nullable=False, server_default=""),
        sa.Column("hearing_type", sa.String(50), nullable=False, server_default="Adjournment"),
        sa.Column("outcome", sa.String(2000), nullable=False, server_default=""),
        sa.Column("next_hearing_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "attachment_id",
            sa.Integer,
            sa.ForeignKey("case_attachments.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "recorded_by_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        *_ts(),
    )
    op.create_index("ix_hearings_case_id", "hearings", ["case_id"])
    op.create_index("ix_hearings_date", "hearings", ["hearing_date"])

    op.create_table(
        "cash_requests",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "case_id",
            sa.Integer,
            sa.ForeignKey("cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("purpose", sa.String(500), nullable=False, server_default=""),
        sa.Column("status", sa.String(20), nullable=False, server_default="Requested"),
        sa.Column(
            "requested_by_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "approved_by_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approval_comment", sa.String(500), nullable=False, server_default=""),
        sa.Column(
            "paid_by_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payment_reference", sa.String(100), nullable=False, server_default=""),
        sa.Column(
            "receipt_attachment_id",
            sa.Integer,
            sa.ForeignKey("case_attachments.id", ondelete="SET NULL"),
            nullable=True,
        ),
        *_ts(),
    )
    op.create_index("ix_cash_requests_case_id", "cash_requests", ["case_id"])
    op.create_index("ix_cash_requests_status", "cash_requests", ["status"])


def downgrade() -> None:
    op.drop_index("ix_cash_requests_status", table_name="cash_requests")
    op.drop_index("ix_cash_requests_case_id", table_name="cash_requests")
    op.drop_table("cash_requests")
    op.drop_index("ix_hearings_date", table_name="hearings")
    op.drop_index("ix_hearings_case_id", table_name="hearings")
    op.drop_table("hearings")
    op.drop_table("court_filings")
