"""Add collection snapshots to proposal and project objects

Revision ID: 0053_object_collection_snapshots
Revises: 0052_merge_0049_0051
Create Date: 2026-08-01
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0053_object_collection_snapshots"
down_revision: str | None = "0052_merge_0049_0051"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "proposal_requested_objects",
        sa.Column("collection_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "proposal_requested_objects",
        sa.Column("collection_name", sa.String(length=255), nullable=True),
    )
    op.create_index(
        op.f("ix_proposal_requested_objects_collection_id"),
        "proposal_requested_objects",
        ["collection_id"],
        unique=False,
    )

    op.add_column(
        "collection_use_objects",
        sa.Column("collection_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "collection_use_objects",
        sa.Column("collection_name", sa.String(length=255), nullable=True),
    )
    op.create_index(
        op.f("ix_collection_use_objects_collection_id"),
        "collection_use_objects",
        ["collection_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_collection_use_objects_collection_id"),
        table_name="collection_use_objects",
    )
    op.drop_column("collection_use_objects", "collection_name")
    op.drop_column("collection_use_objects", "collection_id")

    op.drop_index(
        op.f("ix_proposal_requested_objects_collection_id"),
        table_name="proposal_requested_objects",
    )
    op.drop_column("proposal_requested_objects", "collection_name")
    op.drop_column("proposal_requested_objects", "collection_id")
