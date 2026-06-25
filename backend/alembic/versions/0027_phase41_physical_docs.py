"""Phase 41: physical document chain-of-custody.

Adds three tables:
- ``document_locations`` - master list of storage spots (cabinets,
  safes, lawyer offices).
- ``physical_documents`` - one row per physical asset tied to a case
  (original cheque, ID copy, court filing copy, full case folder).
- ``document_custody_log`` - append-only handover log; latest row
  is mirrored back onto ``physical_documents.current_*``.

Revision ID: 0027_phase41_physical_docs
Revises: 0026_phase40_partners
Create Date: 2026-06-25
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0027_phase41_physical_docs"
down_revision: str | None = "0026_phase40_partners"
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
        "document_locations",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.String(500), nullable=False, server_default=""),
        sa.Column(
            "is_storage", sa.Boolean, nullable=False, server_default=sa.true()
        ),
        sa.Column(
            "is_active", sa.Boolean, nullable=False, server_default=sa.true()
        ),
        *_ts(),
    )
    op.create_index(
        "ix_document_locations_code", "document_locations", ["code"], unique=True
    )

    op.create_table(
        "physical_documents",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "case_id",
            sa.Integer,
            sa.ForeignKey("cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(40), nullable=False, server_default="other"),
        sa.Column("label", sa.String(200), nullable=False),
        sa.Column("notes", sa.Text, nullable=False, server_default=""),
        sa.Column(
            "current_holder_user_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "current_location_id",
            sa.Integer,
            sa.ForeignKey("document_locations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "current_location_text", sa.String(300), nullable=False, server_default=""
        ),
        sa.Column("last_transferred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "is_active", sa.Boolean, nullable=False, server_default=sa.true()
        ),
        *_ts(),
    )
    op.create_index(
        "ix_physical_documents_case_id", "physical_documents", ["case_id"]
    )
    op.create_index(
        "ix_physical_documents_current_holder_user_id",
        "physical_documents",
        ["current_holder_user_id"],
    )

    op.create_table(
        "document_custody_log",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "document_id",
            sa.Integer,
            sa.ForeignKey("physical_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "transferred_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "recorded_by_user_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "from_user_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "to_user_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "location_id",
            sa.Integer,
            sa.ForeignKey("document_locations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "location_text", sa.String(300), nullable=False, server_default=""
        ),
        sa.Column("note", sa.Text, nullable=False, server_default=""),
        sa.Column(
            "signature_filename", sa.String(255), nullable=False, server_default=""
        ),
        sa.Column(
            "signature_stored", sa.String(255), nullable=False, server_default=""
        ),
        sa.Column(
            "signature_mime", sa.String(100), nullable=False, server_default=""
        ),
        sa.Column(
            "signature_size", sa.Integer, nullable=False, server_default="0"
        ),
    )
    op.create_index(
        "ix_document_custody_log_document_id",
        "document_custody_log",
        ["document_id"],
    )
    op.create_index(
        "ix_document_custody_log_transferred_at",
        "document_custody_log",
        ["transferred_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_document_custody_log_transferred_at", table_name="document_custody_log"
    )
    op.drop_index(
        "ix_document_custody_log_document_id", table_name="document_custody_log"
    )
    op.drop_table("document_custody_log")
    op.drop_index(
        "ix_physical_documents_current_holder_user_id",
        table_name="physical_documents",
    )
    op.drop_index(
        "ix_physical_documents_case_id", table_name="physical_documents"
    )
    op.drop_table("physical_documents")
    op.drop_index("ix_document_locations_code", table_name="document_locations")
    op.drop_table("document_locations")
