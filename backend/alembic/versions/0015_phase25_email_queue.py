"""Phase 25: email queue worker + attachment persistence.

Revision ID: 0015_phase25_email_queue
Revises: 0014_phase19_xfer_atts
Create Date: 2026-06-21
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015_phase25_email_queue"
down_revision: str | None = "0014_phase19_xfer_atts"
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
    # 1. Add scheduling columns to email_log
    op.add_column(
        "email_log",
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "email_log",
        sa.Column("last_attempted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_email_log_next_attempt_at",
        "email_log",
        ["next_attempt_at"],
    )
    # Pre-existing rows: mark Queued ones as eligible immediately so
    # the new worker drains the backlog on first tick.
    op.execute(
        "UPDATE email_log SET next_attempt_at = created_at WHERE status = 'Queued'"
    )

    # 2. Attachment persistence
    op.create_table(
        "email_log_attachments",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "email_log_id",
            sa.Integer,
            sa.ForeignKey("email_log.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column(
            "mime_type",
            sa.String(100),
            nullable=False,
            server_default="application/octet-stream",
        ),
        sa.Column("content", sa.LargeBinary, nullable=False),
        sa.Column("size_bytes", sa.Integer, nullable=False, server_default="0"),
        *_ts(),
    )
    op.create_index(
        "ix_email_log_attachments_email_log_id",
        "email_log_attachments",
        ["email_log_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_email_log_attachments_email_log_id",
        table_name="email_log_attachments",
    )
    op.drop_table("email_log_attachments")
    op.drop_index("ix_email_log_next_attempt_at", table_name="email_log")
    op.drop_column("email_log", "last_attempted_at")
    op.drop_column("email_log", "next_attempt_at")
