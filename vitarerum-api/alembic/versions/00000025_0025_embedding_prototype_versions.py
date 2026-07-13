"""Create embedding prototype versions

Revision ID: 0025_embedding_prototypes
Revises: 0024_use_cat_training_examples
Create Date: 2026-07-13
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0025_embedding_prototypes"
down_revision: str | None = "0024_use_cat_training_examples"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "museum_question_embedding_prototype_versions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("embedding_model", sa.String(length=128), nullable=False),
        sa.Column("aggregation_method", sa.String(length=32), nullable=False),
        sa.Column("threshold_profile", sa.JSON(), nullable=False),
        sa.Column("example_ids", sa.JSON(), nullable=False),
        sa.Column("prototypes", sa.JSON(), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("version"),
    )
    op.create_index(
        "ix_museum_question_embedding_prototype_versions_created_at",
        "museum_question_embedding_prototype_versions",
        ["created_at"],
    )
    op.create_index(
        "ix_mq_embedding_prototype_versions_promoted",
        "museum_question_embedding_prototype_versions",
        ["promoted_at", "retired_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_mq_embedding_prototype_versions_promoted",
        table_name="museum_question_embedding_prototype_versions",
    )
    op.drop_index(
        "ix_museum_question_embedding_prototype_versions_created_at",
        table_name="museum_question_embedding_prototype_versions",
    )
    op.drop_table("museum_question_embedding_prototype_versions")
