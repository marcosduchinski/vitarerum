"""Add proposal Direction workflow notification kinds

Revision ID: 0083_direction_notifications
Revises: 0082_proposal_event_target
Create Date: 2026-08-31
"""

from __future__ import annotations

from alembic import op

revision: str = "0083_direction_notifications"
down_revision: str | None = "0082_proposal_event_target"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE notification_kind ADD VALUE IF NOT EXISTS "
        "'PROPOSAL_REFERRED_TO_DIRECTION'"
    )
    op.execute(
        "ALTER TYPE notification_kind ADD VALUE IF NOT EXISTS "
        "'PROPOSAL_RETURNED_TO_STAFF'"
    )


def downgrade() -> None:
    # PostgreSQL enum labels cannot be removed safely in-place.
    pass
