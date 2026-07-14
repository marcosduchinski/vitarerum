"""Require descriptions on collection-use entry attachments

Revision ID: 0029_attachment_desc_required
Revises: 0028_pub_related_object
Create Date: 2026-07-14

Existing empty descriptions are backfilled from the file name. That backfill is
not reversible with fidelity; downgrade only restores the old nullable column
name and shape.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0029_attachment_desc_required"
down_revision: str | None = "0028_pub_related_object"
branch_labels: str | None = None
depends_on: str | None = None

_TABLES = (
    "log_entry_attachments",
    "occurrence_entry_attachments",
    "publication_entry_attachments",
)


def upgrade() -> None:
    for table in _TABLES:
        op.execute(
            f"UPDATE {table} SET note = file_name WHERE note IS NULL OR trim(note) = ''"
        )
        with op.batch_alter_table(table) as batch_op:
            batch_op.alter_column(
                "note",
                new_column_name="description",
                existing_type=sa.Text(),
                nullable=False,
            )


def downgrade() -> None:
    for table in _TABLES:
        with op.batch_alter_table(table) as batch_op:
            batch_op.alter_column(
                "description",
                new_column_name="note",
                existing_type=sa.Text(),
                nullable=True,
            )
