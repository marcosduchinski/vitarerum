"""Allow composite display title mappings

Revision ID: 0038_display_title_columns
Revises: 0037_narrative_prompt_version
Create Date: 2026-07-19
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0038_display_title_columns"
down_revision: str | None = "0037_narrative_prompt_version"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "collection_index_source_document",
        sa.Column(
            "display_title_columns",
            sa.JSON(),
            nullable=False,
            server_default="[]",
        ),
    )
    op.execute(
        """
        UPDATE collection_index_source_document
        SET display_title_columns = json_build_array(display_title_column)
        WHERE display_title_column IS NOT NULL
          AND display_title_column <> ''
        """
    )
    op.alter_column(
        "collection_index_source_document",
        "display_title_columns",
        server_default=None,
    )


def downgrade() -> None:
    op.drop_column("collection_index_source_document", "display_title_columns")

