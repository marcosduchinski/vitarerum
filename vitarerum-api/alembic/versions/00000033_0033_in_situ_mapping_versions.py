"""Persist CIDOC mapping versions on in-situ visit records

Revision ID: 0033_in_situ_mapping_versions
Revises: 0032_narrative_validation
Create Date: 2026-07-17
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0033_in_situ_mapping_versions"
down_revision: str | None = "0032_narrative_validation"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "in_situ_visit_records",
        sa.Column("mapping_version", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "in_situ_visit_records",
        sa.Column("crm_version", sa.String(length=64), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE in_situ_visit_records "
            "SET mapping_version = '0.6.1', crm_version = '7.1.3' "
            "WHERE mapping_version IS NULL AND crm_version IS NULL"
        )
    )


def downgrade() -> None:
    op.drop_column("in_situ_visit_records", "crm_version")
    op.drop_column("in_situ_visit_records", "mapping_version")
