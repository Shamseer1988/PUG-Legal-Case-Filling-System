"""Phase 42: switch the backup engine to pg_dump and add a public
activity log + R2 cloud copies.

Adds three columns to ``backup_jobs``:
- ``format`` - "pgdump" (new default) or "legacy_enc" (old .bkp.enc).
  Restore dispatcher uses this to pick the right path.
- ``sidecar_path`` - filename of the attachments .tar.gz that pairs
  with each .dump (Legal app has uploaded evidence pg_dump can't
  cover).
- ``cloud_path`` - object key in R2/S3 if the backup was pushed
  off-site. Empty when it lives only on local disk.

Adds the ``backup_activity_log`` table that powers the
"Backup activity log" panel on the Backup & Restore screen.

Revision ID: 0028_phase42_pgdump_backup
Revises: 0027_phase41_physical_docs
Create Date: 2026-06-25
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0028_phase42_pgdump_backup"
down_revision: str | None = "0027_phase41_physical_docs"
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
    with op.batch_alter_table("backup_jobs") as batch:
        # Add the column with a temporary "legacy_enc" default so the
        # backfill on existing pre-Phase-42 rows tags them correctly
        # (they were openssl-encrypted .enc bundles). We flip the
        # default to "pgdump" immediately after the batch closes so
        # any NEW inserts match the model default and the restore
        # dispatcher routes them through the pg_restore path.
        batch.add_column(
            sa.Column(
                "format",
                sa.String(length=20),
                nullable=False,
                server_default="legacy_enc",
            )
        )
        batch.add_column(
            sa.Column(
                "sidecar_path",
                sa.String(length=500),
                nullable=False,
                server_default="",
            )
        )
        batch.add_column(
            sa.Column(
                "cloud_path",
                sa.String(length=500),
                nullable=False,
                server_default="",
            )
        )

    op.execute("ALTER TABLE backup_jobs ALTER COLUMN format SET DEFAULT 'pgdump'")

    op.create_table(
        "backup_activity_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            index=True,
        ),
        sa.Column("activity_type", sa.String(length=30), nullable=False, index=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("file_name", sa.String(length=500), nullable=False, default=""),
        sa.Column("cloud_key", sa.String(length=500), nullable=False, default=""),
        sa.Column("message", sa.String(length=1000), nullable=False, default=""),
        sa.Column(
            "actor_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "backup_job_id",
            sa.Integer(),
            sa.ForeignKey("backup_jobs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        *_ts(),
    )


def downgrade() -> None:
    op.drop_table("backup_activity_log")
    with op.batch_alter_table("backup_jobs") as batch:
        batch.drop_column("cloud_path")
        batch.drop_column("sidecar_path")
        batch.drop_column("format")
