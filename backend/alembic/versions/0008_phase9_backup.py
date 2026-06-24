"""Phase 9: backup + restore jobs.

Revision ID: 0008_phase9_backup
Revises: 0007_phase8_audit
Create Date: 2026-06-19
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_phase9_backup"
down_revision: str | None = "0007_phase8_audit"
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
        "backup_jobs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("kind", sa.String(30), nullable=False, server_default="manual"),
        sa.Column("status", sa.String(20), nullable=False, server_default="Queued"),
        sa.Column("storage_path", sa.String(500), nullable=False, server_default=""),
        sa.Column("size_bytes", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("checksum_sha256", sa.String(64), nullable=False, server_default=""),
        sa.Column("is_encrypted", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("table_row_counts", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("attachment_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("manifest", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text, nullable=False, server_default=""),
        sa.Column("notes", sa.String(500), nullable=False, server_default=""),
        sa.Column(
            "created_by_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        *_ts(),
    )
    op.create_index("ix_backup_jobs_status", "backup_jobs", ["status"])

    op.create_table(
        "restore_jobs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "backup_id",
            sa.Integer,
            sa.ForeignKey("backup_jobs.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "safety_snapshot_id",
            sa.Integer,
            sa.ForeignKey("backup_jobs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="Queued"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text, nullable=False, server_default=""),
        sa.Column("tables_restored", sa.Integer, nullable=False, server_default="0"),
        sa.Column("rows_restored", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "created_by_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        *_ts(),
    )
    op.create_index("ix_restore_jobs_backup_id", "restore_jobs", ["backup_id"])
    op.create_index("ix_restore_jobs_status", "restore_jobs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_restore_jobs_status", table_name="restore_jobs")
    op.drop_index("ix_restore_jobs_backup_id", table_name="restore_jobs")
    op.drop_table("restore_jobs")
    op.drop_index("ix_backup_jobs_status", table_name="backup_jobs")
    op.drop_table("backup_jobs")
