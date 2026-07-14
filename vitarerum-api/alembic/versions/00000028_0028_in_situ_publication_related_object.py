"""Add related_object_source_id to in-situ publication records

Revision ID: 0028_in_situ_publication_related_object
Revises: 0027_publication_entry_object_fk
Create Date: 2026-07-14
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0028_in_situ_publication_related_object"
down_revision: str | None = "0027_publication_entry_object_fk"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "in_situ_publication_records",
        sa.Column("related_object_source_id", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("in_situ_publication_records", "related_object_source_id")
