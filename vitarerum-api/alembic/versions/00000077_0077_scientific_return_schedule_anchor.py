"""Add the curator-chosen anchor a review series is measured from.

Revision ID: 0077_sr_schedule_anchor
Revises: 0076_remove_sr_snooze

Reviews used to be measured from whenever the last search happened to run, so a
late search pushed the whole series later. The anchor fixes the grid: reviews
fall on anchor + n x interval, and the curator can move the anchor.

Existing watches are backfilled with their current next_run_at, which is the one
value that leaves every scheduled review exactly where it already is: the
current next_run_at is by construction the first slot of a grid anchored on
itself. No watch changes its next review because of this migration.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0077_sr_schedule_anchor"
down_revision: str | None = "0076_remove_sr_snooze"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "scientific_return_watches",
        sa.Column("schedule_anchor_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE scientific_return_watches "
            "SET schedule_anchor_at = next_run_at "
            "WHERE schedule_anchor_at IS NULL"
        )
    )
    op.alter_column(
        "scientific_return_watches", "schedule_anchor_at", nullable=False
    )


def downgrade() -> None:
    op.drop_column("scientific_return_watches", "schedule_anchor_at")
