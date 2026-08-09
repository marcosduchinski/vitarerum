"""Add museum question response deadlines

Revision ID: 0058_mq_response_deadlines
Revises: 0057_mq_assignment
Create Date: 2026-08-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0058_mq_response_deadlines"
down_revision: str | None = "0057_mq_assignment"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "museum_questions",
        sa.Column("response_due_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "museum_questions",
        sa.Column(
            "response_overdue_notified_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.execute(
        "UPDATE museum_questions "
        "SET response_due_at = created_at + interval '15 days' "
        "WHERE response_due_at IS NULL"
    )
    op.alter_column("museum_questions", "response_due_at", nullable=False)
    op.create_index(
        op.f("ix_museum_questions_status_response_due_at"),
        "museum_questions",
        ["status", "response_due_at"],
        unique=False,
    )
    op.execute(
        "ALTER TYPE notification_kind ADD VALUE IF NOT EXISTS "
        "'MUSEUM_QUESTION_RESPONSE_OVERDUE'"
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_museum_questions_status_response_due_at"),
        table_name="museum_questions",
    )
    op.drop_column("museum_questions", "response_overdue_notified_at")
    op.drop_column("museum_questions", "response_due_at")
    # PostgreSQL cannot remove enum labels without recreating the enum and every
    # dependent column. Leave the extra label in place on downgrade.
