"""Persist CIDOC gate output on narrative fact snapshots

Revision ID: 0034_snapshot_cidoc_gate
Revises: 0033_in_situ_mapping_versions
Create Date: 2026-07-18
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0034_snapshot_cidoc_gate"
down_revision: str | None = "0033_in_situ_mapping_versions"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "narrative_fact_snapshots",
        sa.Column("cidoc_document_json", sa.Text(), nullable=True),
    )
    op.add_column(
        "narrative_fact_snapshots",
        sa.Column("cidoc_validation_report", sa.Text(), nullable=True),
    )
    op.add_column(
        "narrative_fact_snapshots",
        sa.Column("cidoc_conforms", sa.Boolean(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("narrative_fact_snapshots", "cidoc_conforms")
    op.drop_column("narrative_fact_snapshots", "cidoc_validation_report")
    op.drop_column("narrative_fact_snapshots", "cidoc_document_json")
