"""Phase 45: two-phase physical file transfer acceptance flow.

Adds ``transfer_status``, ``accepted_at``, and ``ack_*`` columns to
``document_custody_log`` so transfers to a named user require the
recipient to explicitly accept before custody moves.

Existing rows default to ``transfer_status='accepted'`` (the old
immediate-transfer behaviour) so the migration is backwards-compatible.

Revision ID: 0030_phase45_phys_accept
Revises: 0029_phase44_acct_masters
Create Date: 2026-06-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0030_phase45_phys_accept"
down_revision: str | None = "0029_phase44_acct_masters"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("document_custody_log") as batch:
        batch.add_column(
            sa.Column(
                "transfer_status",
                sa.String(20),
                nullable=False,
                server_default="accepted",
            )
        )
        batch.add_column(
            sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch.add_column(
            sa.Column(
                "ack_filename", sa.String(255), nullable=False, server_default=""
            )
        )
        batch.add_column(
            sa.Column(
                "ack_stored", sa.String(255), nullable=False, server_default=""
            )
        )
        batch.add_column(
            sa.Column("ack_mime", sa.String(100), nullable=False, server_default="")
        )
        batch.add_column(
            sa.Column(
                "ack_size", sa.Integer(), nullable=False, server_default="0"
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("document_custody_log") as batch:
        batch.drop_column("ack_size")
        batch.drop_column("ack_mime")
        batch.drop_column("ack_stored")
        batch.drop_column("ack_filename")
        batch.drop_column("accepted_at")
        batch.drop_column("transfer_status")
