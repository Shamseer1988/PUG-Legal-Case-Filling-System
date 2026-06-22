"""Phase 33: SLA breach notification flag on cases.

Revision ID: 0020_phase33_sla_breach
Revises: 0019_phase32_push_subs
Create Date: 2026-06-22
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020_phase33_sla_breach"
down_revision: str | None = "0019_phase32_push_subs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "cases",
        sa.Column(
            "sla_breach_notified_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("cases", "sla_breach_notified_at")
