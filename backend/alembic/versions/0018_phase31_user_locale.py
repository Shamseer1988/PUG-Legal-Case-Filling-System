"""Phase 31: per-user locale (en / ar).

Revision ID: 0018_phase31_user_locale
Revises: 0017_phase30_case_views
Create Date: 2026-06-22
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018_phase31_user_locale"
down_revision: str | None = "0017_phase30_case_views"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("locale", sa.String(8), nullable=False, server_default="en"),
    )


def downgrade() -> None:
    op.drop_column("users", "locale")
