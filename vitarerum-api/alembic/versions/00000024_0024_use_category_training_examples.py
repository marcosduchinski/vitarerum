"""Create use-category training examples

Revision ID: 0024_use_cat_training_examples
Revises: 0023_journal_entry_object_fk
Create Date: 2026-07-13
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0024_use_cat_training_examples"
down_revision: str | None = "0023_journal_entry_object_fk"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "museum_question_use_category_training_examples",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("triage_id", sa.String(length=36), nullable=False),
        sa.Column("question_id", sa.String(length=36), nullable=False),
        sa.Column("run_number", sa.Integer(), nullable=False),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("superseded_by_example_id", sa.String(length=36), nullable=True),
        sa.Column("human_outcome", sa.String(length=16), nullable=False),
        sa.Column("human_categories", sa.JSON(), nullable=False),
        sa.Column("llm_categories", sa.JSON(), nullable=False),
        sa.Column("embedding_categories", sa.JSON(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("reviewed_by", sa.String(length=255), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("message_hash", sa.String(length=64), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_museum_question_use_category_training_examples_triage_id",
        "museum_question_use_category_training_examples",
        ["triage_id"],
    )
    op.create_index(
        "ix_museum_question_use_category_training_examples_question_id",
        "museum_question_use_category_training_examples",
        ["question_id"],
    )
    op.create_index(
        "ix_museum_question_use_category_training_examples_created_at",
        "museum_question_use_category_training_examples",
        ["created_at"],
    )
    op.create_index(
        "ix_mq_use_category_training_current_triage",
        "museum_question_use_category_training_examples",
        ["triage_id", "superseded_at"],
    )
    op.create_index(
        "ix_mq_use_category_training_active_question",
        "museum_question_use_category_training_examples",
        ["question_id", "active", "superseded_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_mq_use_category_training_active_question",
        table_name="museum_question_use_category_training_examples",
    )
    op.drop_index(
        "ix_mq_use_category_training_current_triage",
        table_name="museum_question_use_category_training_examples",
    )
    op.drop_index(
        "ix_museum_question_use_category_training_examples_created_at",
        table_name="museum_question_use_category_training_examples",
    )
    op.drop_index(
        "ix_museum_question_use_category_training_examples_question_id",
        table_name="museum_question_use_category_training_examples",
    )
    op.drop_index(
        "ix_museum_question_use_category_training_examples_triage_id",
        table_name="museum_question_use_category_training_examples",
    )
    op.drop_table("museum_question_use_category_training_examples")
