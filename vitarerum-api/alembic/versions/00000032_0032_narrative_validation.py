"""Persist narrative validation result

Revision ID: 0032_narrative_validation
Revises: 0031_narrative_fact_snapshots
Create Date: 2026-07-17
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0032_narrative_validation"
down_revision: str | None = "0031_narrative_fact_snapshots"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "generated_narratives",
        sa.Column("validation_conforms", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "generated_narratives",
        sa.Column("validation_findings", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("generated_narratives", "validation_findings")
    op.drop_column("generated_narratives", "validation_conforms")
