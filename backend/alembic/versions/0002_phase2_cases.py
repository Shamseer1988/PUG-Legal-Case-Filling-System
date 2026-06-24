"""Phase 2: cases, cheques, case attachments, yearly case-no sequence.

Revision ID: 0002_phase2_cases
Revises: 0001_phase1
Create Date: 2026-06-19
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_phase2_cases"
down_revision: str | None = "0001_phase1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _ts() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "case_no_sequence",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("last_number", sa.Integer, nullable=False, server_default="0"),
        sa.UniqueConstraint("year", name="uq_case_no_sequence_year"),
    )

    op.create_table(
        "cases",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("case_no", sa.String(40), nullable=False, unique=True),
        sa.Column(
            "customer_id",
            sa.Integer,
            sa.ForeignKey("customers.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "division_id",
            sa.Integer,
            sa.ForeignKey("divisions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "salesman_id",
            sa.Integer,
            sa.ForeignKey("salesmen.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "bank_id",
            sa.Integer,
            sa.ForeignKey("banks.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "case_type_id",
            sa.Integer,
            sa.ForeignKey("case_types.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("customer_type", sa.String(50), nullable=False, server_default="Retail"),
        sa.Column("actual_due_amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("legal_filing_amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("deposit_date", sa.Date, nullable=True),
        sa.Column("is_criminal", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("is_civil", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("commands", sa.String(2000), nullable=False, server_default=""),
        sa.Column("sales_manager_id", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("division_manager_id", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("auditor_id", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("fm_id", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("ed_id", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("chairman_id", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("lawyer_id", sa.Integer, sa.ForeignKey("lawyers.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(40), nullable=False, server_default="Draft"),
        sa.Column("current_stage", sa.String(40), nullable=False, server_default="Accountant"),
        sa.Column("created_by_id", sa.Integer, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        *_ts(),
    )
    op.create_index("ix_cases_case_no", "cases", ["case_no"])
    op.create_index("ix_cases_division_id", "cases", ["division_id"])
    op.create_index("ix_cases_status", "cases", ["status"])

    op.create_table(
        "cheques",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "case_id",
            sa.Integer,
            sa.ForeignKey("cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("cheque_number", sa.String(50), nullable=False),
        sa.Column("bank_id", sa.Integer, sa.ForeignKey("banks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("bank_name_text", sa.String(200), nullable=False, server_default=""),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("cheque_date", sa.Date, nullable=True),
        sa.Column("cheque_type", sa.String(30), nullable=False, server_default="Normal"),
        sa.Column("bounce_reason", sa.String(300), nullable=False, server_default=""),
        *_ts(),
    )
    op.create_index("ix_cheques_case_id", "cheques", ["case_id"])

    op.create_table(
        "case_attachments",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "case_id",
            sa.Integer,
            sa.ForeignKey("cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("stored_filename", sa.String(255), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False, server_default="application/octet-stream"),
        sa.Column("size_bytes", sa.Integer, nullable=False, server_default="0"),
        sa.Column("category", sa.String(50), nullable=False, server_default="Supporting Document"),
        sa.Column(
            "uploaded_by_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        *_ts(),
    )
    op.create_index("ix_case_attachments_case_id", "case_attachments", ["case_id"])


def downgrade() -> None:
    op.drop_index("ix_case_attachments_case_id", table_name="case_attachments")
    op.drop_table("case_attachments")
    op.drop_index("ix_cheques_case_id", table_name="cheques")
    op.drop_table("cheques")
    op.drop_index("ix_cases_status", table_name="cases")
    op.drop_index("ix_cases_division_id", table_name="cases")
    op.drop_index("ix_cases_case_no", table_name="cases")
    op.drop_table("cases")
    op.drop_table("case_no_sequence")
