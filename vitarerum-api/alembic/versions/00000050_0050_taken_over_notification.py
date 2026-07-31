"""Add proposal taken-over notification kind

Revision ID: 0050_taken_over_notification
Revises: 0048_ensure_direction_group
Create Date: 2026-07-31
"""

from __future__ import annotations

from alembic import op

revision: str = "0050_taken_over_notification"
down_revision: str | None = "0048_ensure_direction_group"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE notification_kind ADD VALUE IF NOT EXISTS 'PROPOSAL_TAKEN_OVER'"
    )


def downgrade() -> None:
    # PostgreSQL cannot remove enum labels without recreating the enum and every
    # dependent column. Leave the extra label in place on downgrade.
    pass
