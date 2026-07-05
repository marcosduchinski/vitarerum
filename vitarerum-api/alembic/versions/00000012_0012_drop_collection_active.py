"""Drop the active column from collection_index_collection

Replaces the "deactivate collection" operational concept with outright
removal (SYS_ADMIN hard-deletes a collection and everything under it —
curators, source documents, indexed rows, and their files). There is no
more "inactive" state to track.

Revision ID: 0012_drop_collection_active
Revises: 0011_collection_object_index
Create Date: 2026-07-05
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0012_drop_collection_active"
down_revision: str | None = "0011_collection_object_index"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.drop_column("collection_index_collection", "active")


def downgrade() -> None:
    op.add_column(
        "collection_index_collection",
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
