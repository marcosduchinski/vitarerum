"""Document corrections + public amendment tokens

Revision ID: 0009_document_corrections
Revises: 0008_document_templates
Create Date: 2026-07-03 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009_document_corrections"
down_revision: str | None = "0008_document_templates"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Durable audit of what staff asked to correct/replace/supply. document_id is
    # NULL for a requested *missing* document (document_type is then the scope).
    op.create_table(
        "document_correction_items",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("proposal_id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=True),
        sa.Column("document_type", sa.String(length=128), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="REQUESTED",
        ),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("requested_by", sa.String(length=36), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["proposal_id"], ["proposals.id"]),
    )
    op.create_index(
        "ix_document_correction_items_proposal_id",
        "document_correction_items",
        ["proposal_id"],
    )
    op.create_index(
        "ix_document_correction_items_requested_by",
        "document_correction_items",
        ["requested_by"],
    )

    # Scoped, single-use, expiring token for the public amendment channel. Only
    # the SHA-256 of the raw token is stored; the raw value lives in the e-mail.
    op.create_table(
        "proposal_amendment_tokens",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("proposal_id", sa.String(length=36), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("requester_email", sa.String(length=180), nullable=False),
        sa.Column("correction_item_ids", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_proposal_amendment_tokens_proposal_id",
        "proposal_amendment_tokens",
        ["proposal_id"],
    )
    op.create_index(
        "ix_proposal_amendment_tokens_token_hash",
        "proposal_amendment_tokens",
        ["token_hash"],
        unique=True,
    )
    op.create_index(
        "ix_proposal_amendment_tokens_expires_at",
        "proposal_amendment_tokens",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_proposal_amendment_tokens_expires_at",
        table_name="proposal_amendment_tokens",
    )
    op.drop_index(
        "ix_proposal_amendment_tokens_token_hash",
        table_name="proposal_amendment_tokens",
    )
    op.drop_index(
        "ix_proposal_amendment_tokens_proposal_id",
        table_name="proposal_amendment_tokens",
    )
    op.drop_table("proposal_amendment_tokens")
    op.drop_index(
        "ix_document_correction_items_requested_by",
        table_name="document_correction_items",
    )
    op.drop_index(
        "ix_document_correction_items_proposal_id",
        table_name="document_correction_items",
    )
    op.drop_table("document_correction_items")
