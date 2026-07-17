"""Persist narrative fact snapshots and revisions

Revision ID: 0031_narrative_fact_snapshots
Revises: 0030_in_situ_enriched_snapshot
Create Date: 2026-07-17
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "0031_narrative_fact_snapshots"
down_revision: str | None = "0030_in_situ_enriched_snapshot"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "narrative_fact_snapshots",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("record_id", sa.String(length=36), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("builder_version", sa.String(length=64), nullable=False),
        sa.Column("prompt_version", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_narrative_fact_snapshots_record_id",
        "narrative_fact_snapshots",
        ["record_id"],
    )
    op.create_index(
        "ix_narrative_fact_snapshots_payload_hash",
        "narrative_fact_snapshots",
        ["payload_hash"],
    )
    op.create_index(
        "ix_narrative_fact_snapshots_created_at",
        "narrative_fact_snapshots",
        ["created_at"],
    )

    op.add_column(
        "generated_narratives",
        sa.Column("facts_snapshot_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "generated_narratives",
        sa.Column("prompt_version", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "generated_narratives",
        sa.Column("model_response_hash", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_generated_narratives_facts_snapshot_id",
        "generated_narratives",
        ["facts_snapshot_id"],
    )

    op.create_table(
        "generated_narrative_revisions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("narrative_id", sa.String(length=36), nullable=False),
        sa.Column("previous_narrative", sa.Text(), nullable=False),
        sa.Column("revised_narrative", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_generated_narrative_revisions_narrative_id",
        "generated_narrative_revisions",
        ["narrative_id"],
    )
    op.create_index(
        "ix_generated_narrative_revisions_created_at",
        "generated_narrative_revisions",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_generated_narrative_revisions_created_at",
        table_name="generated_narrative_revisions",
    )
    op.drop_index(
        "ix_generated_narrative_revisions_narrative_id",
        table_name="generated_narrative_revisions",
    )
    op.drop_table("generated_narrative_revisions")

    op.drop_index(
        "ix_generated_narratives_facts_snapshot_id",
        table_name="generated_narratives",
    )
    op.drop_column("generated_narratives", "model_response_hash")
    op.drop_column("generated_narratives", "prompt_version")
    op.drop_column("generated_narratives", "facts_snapshot_id")

    op.drop_index(
        "ix_narrative_fact_snapshots_created_at",
        table_name="narrative_fact_snapshots",
    )
    op.drop_index(
        "ix_narrative_fact_snapshots_payload_hash",
        table_name="narrative_fact_snapshots",
    )
    op.drop_index(
        "ix_narrative_fact_snapshots_record_id",
        table_name="narrative_fact_snapshots",
    )
    op.drop_table("narrative_fact_snapshots")
