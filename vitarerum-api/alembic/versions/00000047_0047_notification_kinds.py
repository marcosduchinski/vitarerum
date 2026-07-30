"""Add staff proposal notification kinds

Revision ID: 0047_notification_kinds
Revises: 0046_notifications
Create Date: 2026-07-30
"""

from __future__ import annotations

from alembic import op

revision: str = "0047_notification_kinds"
down_revision: str | None = "0046_notifications"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE notification_kind ADD VALUE IF NOT EXISTS 'PROPOSAL_SUBMITTED'"
    )
    op.execute(
        "ALTER TYPE notification_kind ADD VALUE IF NOT EXISTS "
        "'PROPOSAL_DOCUMENTS_SUBMITTED'"
    )
    op.execute(
        "ALTER TYPE notification_kind ADD VALUE IF NOT EXISTS "
        "'PROPOSAL_CORRECTIONS_SUBMITTED'"
    )


def downgrade() -> None:
    # PostgreSQL cannot remove enum labels without recreating the enum and every
    # dependent column. Leave the extra labels in place on downgrade.
    pass
