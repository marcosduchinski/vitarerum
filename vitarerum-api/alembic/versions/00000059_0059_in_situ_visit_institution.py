"""Capture the producing institution on in-situ visit records

Revision ID: 0059_in_situ_visit_institution
Revises: 0058_mq_response_deadlines
Create Date: 2026-08-11
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0059_in_situ_visit_institution"
down_revision: str | None = "0058_mq_response_deadlines"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "in_situ_visit_records",
        sa.Column("institution_name", sa.String(length=255), nullable=True),
    )
    # Existing rows are backfilled from place_name, which the export use case
    # has always populated from the same configured institution name, so the
    # two are equal by construction for every record written so far.
    op.execute(
        "UPDATE in_situ_visit_records "
        "SET institution_name = place_name "
        "WHERE institution_name IS NULL"
    )
    op.alter_column(
        "in_situ_visit_records",
        "institution_name",
        nullable=False,
        server_default="",
    )


def downgrade() -> None:
    op.drop_column("in_situ_visit_records", "institution_name")
