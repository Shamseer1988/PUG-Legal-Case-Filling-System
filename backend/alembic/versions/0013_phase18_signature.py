"""Phase 18: signature image + change-password support.

Revision ID: 0013_phase18_signature
Revises: 0012_phase17_lawyer_divisions
Create Date: 2026-06-20
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013_phase18_signature"
down_revision: str | None = "0012_phase17_lawyer_divisions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "signature_path",
            sa.String(500),
            nullable=False,
            server_default="",
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "signature_path")
