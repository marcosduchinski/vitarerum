"""Track narrative revision editor

Revision ID: 0035_revision_edited_by
Revises: 0034_snapshot_cidoc_gate
Create Date: 2026-07-18
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0035_revision_edited_by"
down_revision: str | None = "0034_snapshot_cidoc_gate"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "generated_narrative_revisions",
        sa.Column("edited_by", sa.String(length=36), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("generated_narrative_revisions", "edited_by")
