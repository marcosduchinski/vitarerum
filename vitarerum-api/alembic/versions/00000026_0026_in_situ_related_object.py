"""Add related_object_source_id to in-situ occurrence and log records

Revision ID: 0026_in_situ_related_object
Revises: 0025_embedding_prototypes
Create Date: 2026-07-14
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0026_in_situ_related_object"
down_revision: str | None = "0025_embedding_prototypes"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "in_situ_occurrence_records",
        sa.Column("related_object_source_id", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "in_situ_log_records",
        sa.Column("related_object_source_id", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("in_situ_log_records", "related_object_source_id")
    op.drop_column("in_situ_occurrence_records", "related_object_source_id")
