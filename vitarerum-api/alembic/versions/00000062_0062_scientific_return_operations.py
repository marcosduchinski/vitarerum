"""Add scientific-return operational tracking

Revision ID: 0062_scientific_return_ops
Revises: 0061_scientific_return
Create Date: 2026-08-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0062_scientific_return_ops"
down_revision: str | None = "0061_scientific_return"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "scientific_return_runs",
        sa.Column(
            "new_candidate_count", sa.Integer(), nullable=False, server_default="0"
        ),
    )
    op.add_column(
        "scientific_return_evidences",
        sa.Column("object_id", sa.String(length=36), nullable=True),
    )
    op.create_index(
        "ix_scientific_return_evidences_object_id",
        "scientific_return_evidences",
        ["object_id"],
    )
    op.execute(
        "ALTER TYPE notification_kind ADD VALUE IF NOT EXISTS "
        "'SCIENTIFIC_RETURN_CANDIDATES_FOUND'"
    )


def downgrade() -> None:
    op.drop_index(
        "ix_scientific_return_evidences_object_id",
        table_name="scientific_return_evidences",
    )
    op.drop_column("scientific_return_evidences", "object_id")
    op.drop_column("scientific_return_runs", "new_candidate_count")
    # PostgreSQL enum values are intentionally retained on downgrade.
