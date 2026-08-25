"""Record why a completed full-agentic investigation ran degraded.

A run whose planner contract failed finishes as COMPLETED after the
deterministic floor. Without this column it is indistinguishable from a run
that searched with its full plan and found nothing, which invites a curator to
read absence of results as evidence of absence.

Revision ID: 0073_full_agentic_degraded
Revises: 0072_sr_test_bench
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0073_full_agentic_degraded"
down_revision: str | None = "0072_sr_test_bench"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "sr_full_agentic_investigations",
        sa.Column("degraded_reason", sa.String(length=500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("sr_full_agentic_investigations", "degraded_reason")
