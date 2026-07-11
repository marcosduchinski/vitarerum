"""Allow proposal requested objects without requester

Revision ID: 0021_requested_object_requester
Revises: 0020_mq_triage_classifications
Create Date: 2026-07-11 13:05:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0021_requested_object_requester"
down_revision: str | None = "0020_mq_triage_classifications"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.alter_column(
        "proposal_requested_objects",
        "requested_by",
        existing_type=sa.String(length=36),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "proposal_requested_objects",
        "requested_by",
        existing_type=sa.String(length=36),
        nullable=False,
    )
