"""Add museum question notification enums

Revision ID: 0056_mq_notifications
Revises: 0055_museum_question_attachments
Create Date: 2026-08-09
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0056_mq_notifications"
down_revision: str | None = "0055_museum_question_attachments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE notification_kind ADD VALUE IF NOT EXISTS "
        "'MUSEUM_QUESTION_SUBMITTED'"
    )
    op.execute(
        "ALTER TYPE notification_related_resource_type ADD VALUE IF NOT EXISTS "
        "'MUSEUM_QUESTION'"
    )


def downgrade() -> None:
    # PostgreSQL cannot remove enum labels without recreating the enum and every
    # dependent column. Leave the extra labels in place on downgrade.
    pass
