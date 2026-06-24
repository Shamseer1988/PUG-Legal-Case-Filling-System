"""Phase 5: notifications + email log.

Revision ID: 0005_phase5_notifications
Revises: 0004_phase4_court
Create Date: 2026-06-19
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_phase5_notifications"
down_revision: str | None = "0004_phase4_court"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _ts() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("body", sa.String(2000), nullable=False, server_default=""),
        sa.Column("link", sa.String(500), nullable=False, server_default=""),
        sa.Column("event", sa.String(50), nullable=False, server_default=""),
        sa.Column(
            "related_case_id",
            sa.Integer,
            sa.ForeignKey("cases.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("is_read", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        *_ts(),
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.create_index("ix_notifications_is_read", "notifications", ["is_read"])

    op.create_table(
        "email_log",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("to_emails", sa.String(1000), nullable=False),
        sa.Column("cc_emails", sa.String(1000), nullable=False, server_default=""),
        sa.Column("bcc_emails", sa.String(1000), nullable=False, server_default=""),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column(
            "template_name",
            sa.String(100),
            nullable=False,
            server_default="notification_email.html",
        ),
        sa.Column("body_html", sa.Text, nullable=False, server_default=""),
        sa.Column("body_text", sa.Text, nullable=False, server_default=""),
        sa.Column("status", sa.String(20), nullable=False, server_default="Queued"),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error", sa.Text, nullable=False, server_default=""),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("event", sa.String(50), nullable=False, server_default=""),
        sa.Column(
            "related_case_id",
            sa.Integer,
            sa.ForeignKey("cases.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "related_user_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        *_ts(),
    )
    op.create_index("ix_email_log_status", "email_log", ["status"])


def downgrade() -> None:
    op.drop_index("ix_email_log_status", table_name="email_log")
    op.drop_table("email_log")
    op.drop_index("ix_notifications_is_read", table_name="notifications")
    op.drop_index("ix_notifications_user_id", table_name="notifications")
    op.drop_table("notifications")
