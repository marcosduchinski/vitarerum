"""Add searchable column selection to source documents

Revision ID: 0039_source_searchable_columns
Revises: 0038_display_title_columns
Create Date: 2026-07-19
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0039_source_searchable_columns"
down_revision: str | None = "0038_display_title_columns"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "collection_index_source_document",
        sa.Column(
            "searchable_columns",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
    )
    op.add_column(
        "collection_index_source_document",
        sa.Column(
            "content_matches_searchable_columns",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.execute(
        """
        WITH column_keys AS (
            SELECT
                source_document_id,
                jsonb_agg(column_name ORDER BY lower(column_name)) AS columns
            FROM (
                SELECT DISTINCT
                    source_document_id,
                    jsonb_object_keys(cells) AS column_name
                FROM collection_index_object
            ) distinct_columns
            GROUP BY source_document_id
        )
        UPDATE collection_index_source_document AS document
        SET searchable_columns = column_keys.columns
        FROM column_keys
        WHERE document.id = column_keys.source_document_id
        """
    )
    op.execute(
        """
        WITH fallback_columns AS (
            SELECT id, jsonb_agg(column_name ORDER BY first_seen) AS columns
            FROM (
                SELECT id, column_name, min(ordinality) AS first_seen
                FROM collection_index_source_document
                CROSS JOIN LATERAL unnest(
                    ARRAY_REMOVE(ARRAY[inventory_number_column], NULL)
                    || COALESCE(
                        ARRAY(
                            SELECT jsonb_array_elements_text(
                                display_title_columns::jsonb
                            )
                        ),
                        ARRAY[]::text[]
                    )
                    || CASE
                        WHEN display_title_columns::jsonb = '[]'::jsonb
                         AND display_title_column IS NOT NULL
                        THEN ARRAY[display_title_column]
                        ELSE ARRAY[]::text[]
                    END
                    || ARRAY_REMOVE(ARRAY[object_name_column], NULL)
                    || COALESCE(
                        ARRAY(
                            SELECT jsonb_array_elements_text(
                                description_columns::jsonb
                            )
                        ),
                        ARRAY[]::text[]
                    )
                ) WITH ORDINALITY AS candidate(column_name, ordinality)
                WHERE searchable_columns = '[]'::jsonb
                GROUP BY id, column_name
            ) deduplicated
            GROUP BY id
        )
        UPDATE collection_index_source_document AS document
        SET searchable_columns = fallback_columns.columns
        FROM fallback_columns
        WHERE document.id = fallback_columns.id
          AND fallback_columns.columns <> '[]'::jsonb
        """
    )
    op.execute(
        """
        UPDATE collection_index_source_document
        SET content_matches_searchable_columns = false
        """
    )
    op.alter_column(
        "collection_index_source_document",
        "searchable_columns",
        server_default=None,
    )
    op.alter_column(
        "collection_index_source_document",
        "content_matches_searchable_columns",
        server_default=None,
    )


def downgrade() -> None:
    op.drop_column(
        "collection_index_source_document", "content_matches_searchable_columns"
    )
    op.drop_column("collection_index_source_document", "searchable_columns")
