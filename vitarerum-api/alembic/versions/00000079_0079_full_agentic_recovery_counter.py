"""Count how often a full-agentic investigation had to be recovered.

Revision ID: 0079_full_agentic_recovery
Revises: 0078_sr_abandoned_reason

A worker that dies leaves its row claimable again, which is what makes the flow
resumable — and, with nothing counting those take-overs, also what let a single
poisoned investigation return to the head of the queue forever while blocking
every new investigation of the same project. The counter is the evidence that
the work itself, rather than the infrastructure, is the problem.

Existing rows start at zero: whatever recoveries they have already had are not
recorded anywhere, and charging them for history they cannot show would
terminate live work on a number nobody can audit.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0079_full_agentic_recovery"
down_revision: str | None = "0078_sr_abandoned_reason"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "sr_full_agentic_investigations"


def upgrade() -> None:
    op.add_column(
        _TABLE,
        sa.Column(
            "recovery_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        _TABLE,
        sa.Column("last_recovered_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        _TABLE,
        sa.Column("last_recovery_reason", sa.String(200), nullable=True),
    )
    # The reaper and the queue both look for old live rows; the index keeps that
    # scan off the whole table as the trajectory history grows.
    op.create_index(
        "ix_sr_full_agentic_status_created",
        _TABLE,
        ["status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_sr_full_agentic_status_created", table_name=_TABLE)
    op.drop_column(_TABLE, "last_recovery_reason")
    op.drop_column(_TABLE, "last_recovered_at")
    op.drop_column(_TABLE, "recovery_count")
