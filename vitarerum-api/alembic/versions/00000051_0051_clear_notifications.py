"""Add notification clearing timestamp

Revision ID: 0051_clear_notifications
Revises: 0050_taken_over_notification
Create Date: 2026-07-31
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0051_clear_notifications"
down_revision: str | None = "0050_taken_over_notification"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "notifications",
        sa.Column("cleared_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("notifications", "cleared_at")
