"""Create document_templates table

Backs the Document Templates context: staff-curated .docx forms offered per
UseType on the public submission screen.

Revision ID: 0008_document_templates
Revises: 0007_drop_use_description
Create Date: 2026-07-02
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0008_document_templates"
down_revision: str | None = "0007_drop_use_description"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "document_templates",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("use_type", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "mandatory",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "display_order",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("file_reference", sa.String(length=512), nullable=False),
        sa.Column("uploaded_by", sa.String(length=36), nullable=False),
        sa.Column(
            "uploaded_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_document_templates_use_type",
        "document_templates",
        ["use_type"],
    )
    op.create_index(
        "ix_document_templates_active",
        "document_templates",
        ["active"],
    )


def downgrade() -> None:
    op.drop_index("ix_document_templates_active", table_name="document_templates")
    op.drop_index("ix_document_templates_use_type", table_name="document_templates")
    op.drop_table("document_templates")
