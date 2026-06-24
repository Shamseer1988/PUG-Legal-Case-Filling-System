"""Phase 37: users.is_all_divisions flag.

Mirrors the existing Lawyer.is_all_divisions column so an admin
can mark a user as cross-division without having to maintain a
per-division mapping (or grant them is_super).

Revision ID: 0024_phase37_user_all_divs
Revises: 0023_phase36_cheque_atts
Create Date: 2026-06-22
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024_phase37_user_all_divs"
down_revision: str | None = "0023_phase36_cheque_atts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "is_all_divisions",
            sa.Boolean,
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "is_all_divisions")
