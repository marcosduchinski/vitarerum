"""Create the museum_questions table

Backs the Museum Questions context: public "Pergunte ao Museu" intake
(museum-questions-public-page-plan.md). Includes the answer/out-of-scope/
close audit columns up front, even though only SUBMITTED rows are produced
by this plan, so the internal response section
(museum-questions-response-section-plan.md) needs no migration of its own.

Revision ID: 0013_museum_questions
Revises: 0012_drop_collection_active
Create Date: 2026-07-05
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0013_museum_questions"
down_revision: str | None = "0012_drop_collection_active"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "museum_questions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("requester_name", sa.String(length=120), nullable=False),
        sa.Column("requester_email", sa.String(length=180), nullable=False),
        sa.Column("subject", sa.String(length=200), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("answered_by", sa.String(length=36), nullable=True),
        sa.Column("answer_body", sa.Text(), nullable=True),
        sa.Column("answer_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("out_of_scope_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("out_of_scope_by", sa.String(length=36), nullable=True),
        sa.Column("out_of_scope_reason", sa.Text(), nullable=True),
        sa.Column(
            "out_of_scope_email_sent_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_by", sa.String(length=36), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_museum_questions_status", "museum_questions", ["status"]
    )
    op.create_index(
        "ix_museum_questions_created_at", "museum_questions", ["created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_museum_questions_created_at", table_name="museum_questions")
    op.drop_index("ix_museum_questions_status", table_name="museum_questions")
    op.drop_table("museum_questions")
