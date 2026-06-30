"""Add proposed_begin_date / proposed_end_date to public_proposal_submissions

Captures the dates a citizen proposes for the use on a pending public
submission, seeding the materialised proposal's begin/end on confirm. Both
columns are optional, so they are added nullable with no backfill.

Revision ID: 0003_public_proposed_dates
Revises: 0002_public_use_type
Create Date: 2026-06-30 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003_public_proposed_dates"
down_revision: str | None = "0002_public_use_type"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE public_proposal_submissions ADD COLUMN proposed_begin_date DATE"
    )
    op.execute(
        "ALTER TABLE public_proposal_submissions ADD COLUMN proposed_end_date DATE"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE public_proposal_submissions DROP COLUMN proposed_end_date"
    )
    op.execute(
        "ALTER TABLE public_proposal_submissions DROP COLUMN proposed_begin_date"
    )
