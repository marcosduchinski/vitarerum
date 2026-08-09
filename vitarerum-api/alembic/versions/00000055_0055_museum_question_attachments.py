"""Add museum question image attachments

Revision ID: 0055_museum_question_attachments
Revises: 0054_db_field_encryption_p1
Create Date: 2026-08-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0055_museum_question_attachments"
down_revision: str | None = "0054_db_field_encryption_p1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "museum_question_attachments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("question_id", sa.String(length=36), nullable=False),
        sa.Column("file_name", sa.Text(), nullable=False),
        sa.Column("file_reference", sa.String(length=512), nullable=False),
        sa.Column("content_type", sa.String(length=32), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["question_id"], ["museum_questions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_museum_question_attachments_question_id"),
        "museum_question_attachments",
        ["question_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_museum_question_attachments_created_at"),
        "museum_question_attachments",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_museum_question_attachments_created_at"),
        table_name="museum_question_attachments",
    )
    op.drop_index(
        op.f("ix_museum_question_attachments_question_id"),
        table_name="museum_question_attachments",
    )
    op.drop_table("museum_question_attachments")
