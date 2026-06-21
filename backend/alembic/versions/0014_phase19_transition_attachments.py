"""Phase 19: per-transition approval-comment attachments.

Revision ID: 0014_phase19_transition_attachments
Revises: 0013_phase18_signature
Create Date: 2026-06-20
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014_phase19_transition_attachments"
down_revision: str | None = "0013_phase18_signature"
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
        "case_transition_attachments",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "case_id",
            sa.Integer,
            sa.ForeignKey("cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "transition_id",
            sa.Integer,
            sa.ForeignKey("case_status_updates.id", ondelete="CASCADE"),
            nullable=True,
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
            "uploaded_by_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        *_ts(),
    )
    op.create_index(
        "ix_case_transition_attachments_case_id",
        "case_transition_attachments",
        ["case_id"],
    )
    op.create_index(
        "ix_case_transition_attachments_transition_id",
        "case_transition_attachments",
        ["transition_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_case_transition_attachments_transition_id",
        table_name="case_transition_attachments",
    )
    op.drop_index(
        "ix_case_transition_attachments_case_id",
        table_name="case_transition_attachments",
    )
    op.drop_table("case_transition_attachments")
