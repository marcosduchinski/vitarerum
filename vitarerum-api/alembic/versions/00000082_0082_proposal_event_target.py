"""Add proposal event target permission

Revision ID: 0082_proposal_event_target
Revises: 0081_full_agentic_object
Create Date: 2026-08-31
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0082_proposal_event_target"
down_revision: str | None = "0081_full_agentic_object"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "proposal_events",
        sa.Column("target_permission_id", sa.String(length=36), nullable=True),
    )
    op.create_index(
        "ix_proposal_events_target_permission_id",
        "proposal_events",
        ["target_permission_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_proposal_events_target_permission_id", table_name="proposal_events"
    )
    op.drop_column("proposal_events", "target_permission_id")
