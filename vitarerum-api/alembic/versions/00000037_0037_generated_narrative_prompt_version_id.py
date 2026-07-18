"""Track AI prompt version used by generated narratives

Revision ID: 0037_narrative_prompt_version
Revises: 0036_ai_prompts
Create Date: 2026-07-18
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0037_narrative_prompt_version"
down_revision: str | None = "0036_ai_prompts"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "generated_narratives",
        sa.Column("prompt_version_id", sa.String(length=36), nullable=True),
    )
    op.create_index(
        "ix_generated_narratives_prompt_version_id",
        "generated_narratives",
        ["prompt_version_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_generated_narratives_prompt_version_id",
        table_name="generated_narratives",
    )
    op.drop_column("generated_narratives", "prompt_version_id")
