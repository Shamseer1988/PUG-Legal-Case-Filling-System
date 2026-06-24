"""Phase 13: case closure table.

Revision ID: 0011_phase13_closure
Revises: 0010_phase12_2fa
Create Date: 2026-06-20
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_phase13_closure"
down_revision: str | None = "0010_phase12_2fa"
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
        "case_closures",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "case_id",
            sa.Integer,
            sa.ForeignKey("cases.id", ondelete="CASCADE"),
            unique=True,
            nullable=False,
        ),
        sa.Column("closure_type", sa.String(30), nullable=False),
        sa.Column("command", sa.Text, nullable=False, server_default=""),
        sa.Column("settled_amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("settled_date", sa.Date, nullable=True),
        sa.Column("court_cheque_number", sa.String(60), nullable=False, server_default=""),
        sa.Column("court_cheque_bank", sa.String(200), nullable=False, server_default=""),
        sa.Column("court_cheque_date", sa.Date, nullable=True),
        sa.Column("transfer_reference", sa.String(120), nullable=False, server_default=""),
        sa.Column("transfer_bank", sa.String(200), nullable=False, server_default=""),
        sa.Column("transfer_account_last4", sa.String(8), nullable=False, server_default=""),
        sa.Column("cash_receipt_no", sa.String(60), nullable=False, server_default=""),
        sa.Column(
            "cash_received_by_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "settlement_agreement_ref", sa.String(120), nullable=False, server_default=""
        ),
        sa.Column("writeoff_reason", sa.Text, nullable=False, server_default=""),
        sa.Column("extra", sa.JSON, nullable=False, server_default="{}"),
        sa.Column(
            "closed_by_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=False),
        *_ts(),
    )
    op.create_index("ix_case_closures_case_id", "case_closures", ["case_id"])


def downgrade() -> None:
    op.drop_index("ix_case_closures_case_id", table_name="case_closures")
    op.drop_table("case_closures")
