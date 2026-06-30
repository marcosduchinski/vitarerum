"""Add use_type to public_proposal_submissions

Captures the citizen's intended use (shared UseType taxonomy) on a pending public
submission, so it can seed the materialised proposal's IntendedUse on confirm. The
column is added nullable, backfilled to OTHER for any in-flight pending rows, then
made NOT NULL — safe on a populated database.

Revision ID: 0002_add_use_type_to_public_submissions
Revises: 0001_add_institutions
Create Date: 2026-06-30 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002_add_use_type_to_public_submissions"
down_revision: str | None = "0001_add_institutions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add nullable, backfill in-flight pending rows to OTHER, then constrain.
    op.execute(
        "ALTER TABLE public_proposal_submissions ADD COLUMN use_type VARCHAR(32)"
    )
    op.execute(
        "UPDATE public_proposal_submissions SET use_type = 'OTHER' "
        "WHERE use_type IS NULL"
    )
    op.execute(
        "ALTER TABLE public_proposal_submissions "
        "ALTER COLUMN use_type SET NOT NULL"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE public_proposal_submissions DROP COLUMN use_type")
