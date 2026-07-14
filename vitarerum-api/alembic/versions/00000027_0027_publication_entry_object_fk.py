"""Add optional collection_use_object_id to publication log entries

Revision ID: 0027_publication_entry_object_fk
Revises: 0026_in_situ_related_object
Create Date: 2026-07-14
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0027_publication_entry_object_fk"
down_revision: str | None = "0026_in_situ_related_object"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "publication_log_entries",
        sa.Column("collection_use_object_id", sa.String(length=36), nullable=True),
    )
    op.create_index(
        "ix_publication_log_entries_collection_use_object_id",
        "publication_log_entries",
        ["collection_use_object_id"],
    )
    op.create_foreign_key(
        "fk_publication_log_entries_collection_use_object_id",
        "publication_log_entries",
        "collection_use_objects",
        ["collection_use_object_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_publication_log_entries_collection_use_object_id",
        "publication_log_entries",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_publication_log_entries_collection_use_object_id",
        table_name="publication_log_entries",
    )
    op.drop_column("publication_log_entries", "collection_use_object_id")
