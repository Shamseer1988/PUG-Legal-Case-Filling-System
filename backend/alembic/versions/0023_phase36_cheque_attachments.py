"""Phase 36: cheque-level attachments + OCR audit trail.

Revision ID: 0023_phase36_cheque_atts
Revises: 0022_phase35_job_runs
Create Date: 2026-06-22
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023_phase36_cheque_atts"
down_revision: str | None = "0022_phase35_job_runs"
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
        "cheque_attachments",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "cheque_id",
            sa.Integer,
            sa.ForeignKey("cheques.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "case_id",
            sa.Integer,
            sa.ForeignKey("cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("stored_filename", sa.String(255), nullable=False),
        sa.Column(
            "mime_type",
            sa.String(100),
            nullable=False,
            server_default="application/octet-stream",
        ),
        sa.Column("size_bytes", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "is_bank_return_letter",
            sa.Boolean,
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("ocr_extracted_json", sa.Text, nullable=False, server_default=""),
        sa.Column(
            "uploaded_by_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        *_ts(),
    )
    op.create_index(
        "ix_cheque_attachments_cheque_id", "cheque_attachments", ["cheque_id"]
    )
    op.create_index(
        "ix_cheque_attachments_case_id", "cheque_attachments", ["case_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_cheque_attachments_case_id", table_name="cheque_attachments")
    op.drop_index(
        "ix_cheque_attachments_cheque_id", table_name="cheque_attachments"
    )
    op.drop_table("cheque_attachments")
