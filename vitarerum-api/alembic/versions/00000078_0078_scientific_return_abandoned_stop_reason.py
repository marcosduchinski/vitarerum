"""Add the ABANDONED stop reason.

Revision ID: 0078_sr_abandoned_reason
Revises: 0077_sr_schedule_anchor

A supervised cycle is synchronous, so a process that dies mid-cycle leaves its
investigation non-terminal for good, and a live row blocks every future
investigation of the same target. The scheduled sweep now closes those, and the
module's invariant is that every investigation ends with a typed reason, so
closing one needs a reason of its own rather than borrowing an unrelated failure.

Adding a value to a Postgres enum is not transactional in older versions, so the
statement is issued with IF NOT EXISTS and the downgrade is a no-op: removing an
enum value would require rebuilding the type and rewriting rows that legitimately
carry it.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0078_sr_abandoned_reason"
down_revision: str | None = "0077_sr_schedule_anchor"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "ALTER TYPE scientific_return_stop_reason ADD VALUE IF NOT EXISTS "
            "'ABANDONED'"
        )
    )


def downgrade() -> None:
    # Intentionally empty: an unused enum value is harmless, and dropping one
    # would mean rebuilding the type and deciding what to do with the rows that
    # already record an abandoned cycle.
    pass
