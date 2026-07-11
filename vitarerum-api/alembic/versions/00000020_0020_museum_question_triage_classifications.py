"""Create museum_question_triage_classifications

Backs the cascade classification plan's Fase 0: use-category classification
runs are stored as child rows of museum_question_triages, one row per
classifier execution.

Revision ID: 0020_mq_triage_classifications
Revises: 0019_triage_overrides
Create Date: 2026-07-10
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0020_mq_triage_classifications"
down_revision: str | None = "0019_triage_overrides"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "museum_question_triage_classifications",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("triage_id", sa.String(length=36), nullable=False),
        sa.Column("classifier_kind", sa.String(length=16), nullable=False),
        sa.Column("classifier_model", sa.String(length=128), nullable=True),
        sa.Column("classifier_version", sa.String(length=128), nullable=True),
        sa.Column("run_number", sa.Integer(), nullable=False),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=True),
        sa.Column("quality", sa.String(length=16), nullable=True),
        sa.Column("category_scores", sa.JSON(), nullable=False),
        sa.Column("assigned_categories", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("classified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_museum_question_triage_classifications_triage_id",
        "museum_question_triage_classifications",
        ["triage_id"],
    )
    op.create_index(
        "ix_museum_question_triage_classifications_created_at",
        "museum_question_triage_classifications",
        ["created_at"],
    )
    op.create_index(
        "ix_mq_triage_classifications_current",
        "museum_question_triage_classifications",
        ["triage_id", "classifier_kind", "superseded_at"],
    )
    op.create_index(
        "ix_mq_triage_classifications_pending",
        "museum_question_triage_classifications",
        ["status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_mq_triage_classifications_pending",
        table_name="museum_question_triage_classifications",
    )
    op.drop_index(
        "ix_mq_triage_classifications_current",
        table_name="museum_question_triage_classifications",
    )
    op.drop_index(
        "ix_museum_question_triage_classifications_created_at",
        table_name="museum_question_triage_classifications",
    )
    op.drop_index(
        "ix_museum_question_triage_classifications_triage_id",
        table_name="museum_question_triage_classifications",
    )
    op.drop_table("museum_question_triage_classifications")
