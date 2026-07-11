"""Add object snapshot mapping to source documents

Revision ID: 0022_source_doc_obj_map
Revises: 0021_requested_object_requester
Create Date: 2026-07-11
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0022_source_doc_obj_map"
down_revision: str | None = "0021_requested_object_requester"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "collection_index_source_document",
        sa.Column("inventory_number_column", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "collection_index_source_document",
        sa.Column("display_title_column", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "collection_index_source_document",
        sa.Column("object_name_column", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "collection_index_source_document",
        sa.Column(
            "description_columns",
            sa.JSON(),
            nullable=False,
            server_default="[]",
        ),
    )
    op.alter_column(
        "collection_index_source_document",
        "description_columns",
        server_default=None,
    )


def downgrade() -> None:
    op.drop_column("collection_index_source_document", "description_columns")
    op.drop_column("collection_index_source_document", "object_name_column")
    op.drop_column("collection_index_source_document", "display_title_column")
    op.drop_column("collection_index_source_document", "inventory_number_column")
