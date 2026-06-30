"""Make proposed_begin_date / proposed_end_date required on public submissions

The public submit endpoint now requires both proposed dates. Backfill any
in-flight pending rows (created while the columns were optional) from their
created_at date, then enforce NOT NULL — safe on a populated database.

Revision ID: 0004_public_dates_required
Revises: 0003_public_proposed_dates
Create Date: 2026-06-30 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004_public_dates_required"
down_revision: str | None = "0003_public_proposed_dates"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Backfill legacy rows that predate the requirement, then constrain.
    op.execute(
        "UPDATE public_proposal_submissions "
        "SET proposed_begin_date = CAST(created_at AS DATE) "
        "WHERE proposed_begin_date IS NULL"
    )
    op.execute(
        "UPDATE public_proposal_submissions "
        "SET proposed_end_date = CAST(created_at AS DATE) "
        "WHERE proposed_end_date IS NULL"
    )
    op.execute(
        "ALTER TABLE public_proposal_submissions "
        "ALTER COLUMN proposed_begin_date SET NOT NULL"
    )
    op.execute(
        "ALTER TABLE public_proposal_submissions "
        "ALTER COLUMN proposed_end_date SET NOT NULL"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE public_proposal_submissions "
        "ALTER COLUMN proposed_end_date DROP NOT NULL"
    )
    op.execute(
        "ALTER TABLE public_proposal_submissions "
        "ALTER COLUMN proposed_begin_date DROP NOT NULL"
    )
