"""Add museum question assignment

Revision ID: 0057_mq_assignment
Revises: 0056_mq_notifications
Create Date: 2026-08-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0057_mq_assignment"
down_revision: str | None = "0056_mq_notifications"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "museum_questions",
        sa.Column("assigned_to", sa.String(length=36), nullable=True),
    )
    op.create_index(
        op.f("ix_museum_questions_assigned_to"),
        "museum_questions",
        ["assigned_to"],
        unique=False,
    )
    op.execute(
        "ALTER TYPE notification_kind ADD VALUE IF NOT EXISTS "
        "'MUSEUM_QUESTION_FORWARDED'"
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_museum_questions_assigned_to"), table_name="museum_questions"
    )
    op.drop_column("museum_questions", "assigned_to")
    # PostgreSQL cannot remove enum labels without recreating the enum and every
    # dependent column. Leave the extra label in place on downgrade.
