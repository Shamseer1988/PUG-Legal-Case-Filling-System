"""Phase 34: hearing reminder columns.

Revision ID: 0021_phase34_hearing_reminders
Revises: 0020_phase33_sla_breach
Create Date: 2026-06-22
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021_phase34_hearing_reminders"
down_revision: str | None = "0020_phase33_sla_breach"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "hearings",
        sa.Column("reminder_24h_sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "hearings",
        sa.Column("reminder_1h_sent_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("hearings", "reminder_1h_sent_at")
    op.drop_column("hearings", "reminder_24h_sent_at")
