"""Add FK from journal entries to collection_use_objects

Revision ID: 0023_journal_entry_object_fk
Revises: 0022_source_doc_obj_map
Create Date: 2026-07-12
"""

from __future__ import annotations

from alembic import op

revision: str = "0023_journal_entry_object_fk"
down_revision: str | None = "0022_source_doc_obj_map"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_foreign_key(
        "fk_object_log_entries_collection_use_object_id",
        "object_log_entries",
        "collection_use_objects",
        ["collection_use_object_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_object_occurrence_entries_collection_use_object_id",
        "object_occurrence_entries",
        "collection_use_objects",
        ["collection_use_object_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_object_occurrence_entries_collection_use_object_id",
        "object_occurrence_entries",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_object_log_entries_collection_use_object_id",
        "object_log_entries",
        type_="foreignkey",
    )
