"""Create the museum_question_triages table

Backs the Museum Question Triage context (docs/plans/museum-questions-ai-
triage-plan.md): one immutable row per AI triage run over a museum question,
keyed by `question_id` (plain string, no cross-context FK — same convention
as `generated_narratives.record_id`).

Revision ID: 0015_museum_question_triages
Revises: 0014_collection_areas
Create Date: 2026-07-07
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0015_museum_question_triages"
down_revision: str | None = "0014_collection_areas"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "museum_question_triages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("question_id", sa.String(length=36), nullable=False),
        sa.Column("verdict", sa.String(length=16), nullable=False),
        sa.Column("is_visit_related", sa.Boolean(), nullable=False),
        sa.Column("mentioned_objects", sa.JSON(), nullable=False),
        sa.Column("object_matches", sa.JSON(), nullable=False),
        sa.Column("suggested_reply", sa.Text(), nullable=True),
        sa.Column("llm_model", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_museum_question_triages_question_id",
        "museum_question_triages",
        ["question_id"],
    )
    op.create_index(
        "ix_museum_question_triages_created_at",
        "museum_question_triages",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_museum_question_triages_created_at",
        table_name="museum_question_triages",
    )
    op.drop_index(
        "ix_museum_question_triages_question_id",
        table_name="museum_question_triages",
    )
    op.drop_table("museum_question_triages")
