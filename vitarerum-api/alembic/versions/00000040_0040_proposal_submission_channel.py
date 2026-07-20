"""Add proposal submission channel

Revision ID: 0040_proposal_submission_channel
Revises: 0039_source_searchable_columns
Create Date: 2026-07-20
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0040_proposal_submission_channel"
down_revision: str | None = "0039_source_searchable_columns"
branch_labels: str | None = None
depends_on: str | None = None

submission_channel_enum = sa.Enum(
    "PUBLIC",
    "AUTHENTICATED",
    name="proposal_submission_channel",
)


def upgrade() -> None:
    bind = op.get_bind()
    submission_channel_enum.create(bind, checkfirst=True)
    op.add_column(
        "proposals",
        sa.Column("submission_channel", submission_channel_enum, nullable=True),
    )
    op.execute(
        """
        UPDATE proposals
        SET submission_channel = 'PUBLIC'
        WHERE requester_name IS NOT NULL OR requester_email IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE proposals
        SET submission_channel = 'AUTHENTICATED'
        WHERE requester_name IS NULL AND requester_email IS NULL
        """
    )
    op.alter_column("proposals", "submission_channel", nullable=False)


def downgrade() -> None:
    bind = op.get_bind()
    op.drop_column("proposals", "submission_channel")
    submission_channel_enum.drop(bind, checkfirst=True)
