"""Add supervised scientific-return monitoring

Revision ID: 0061_scientific_return
Revises: 0060_staff_project_todo_items
Create Date: 2026-08-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0061_scientific_return"
down_revision: str | None = "0060_staff_project_todo_items"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _enum(name: str, *values: str) -> postgresql.ENUM:
    return postgresql.ENUM(*values, name=name, create_type=False)


def upgrade() -> None:
    watch_status = _enum("scientific_return_watch_status", "ACTIVE", "PAUSED", "CLOSED")
    run_status = _enum("scientific_return_run_status", "RUNNING", "COMPLETED", "FAILED")
    query_status = _enum("scientific_return_query_status", "COMPLETED", "FAILED")
    query_type = _enum(
        "scientific_return_query_type",
        "INVENTORY",
        "AUTHOR_INVENTORY",
        "INVENTORY_OBJECT",
        "AUTHOR_OBJECT",
    )
    candidate_status = _enum(
        "scientific_return_candidate_status",
        "PENDING",
        "CONFIRMED",
        "DISMISSED",
        "SNOOZED",
    )
    evidence_type = _enum(
        "scientific_return_evidence_type",
        "INVENTORY_NUMBER",
        "AUTHOR",
        "OBJECT_NAME",
        "AUTHOR_INVENTORY",
        "INVENTORY_OBJECT",
        "AUTHOR_OBJECT",
    )
    evidence_strength = _enum(
        "scientific_return_evidence_strength", "PRIMARY", "SUPPORTING", "WEAK"
    )
    decision_type = _enum(
        "scientific_return_decision_type",
        "CONFIRM",
        "CORRECT_AND_CONFIRM",
        "DISMISS",
        "SNOOZE",
    )
    enums = (
        watch_status,
        run_status,
        query_status,
        query_type,
        candidate_status,
        evidence_type,
        evidence_strength,
        decision_type,
    )
    for enum in enums:
        enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "scientific_return_snapshots",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("builder_version", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_scientific_return_snapshots_project_id",
        "scientific_return_snapshots",
        ["project_id"],
    )
    op.create_index(
        "ix_scientific_return_snapshots_payload_hash",
        "scientific_return_snapshots",
        ["payload_hash"],
    )

    op.create_table(
        "scientific_return_watches",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("status", watch_status, nullable=False),
        sa.Column("review_interval_days", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("project_snapshot_id", sa.String(length=36), nullable=False),
        sa.CheckConstraint(
            "review_interval_days between 1 and 365",
            name="ck_scientific_return_watch_interval",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["collection_use_projects.id"],
            name="fk_scientific_return_watch_project",
        ),
        sa.ForeignKeyConstraint(
            ["project_snapshot_id"],
            ["scientific_return_snapshots.id"],
            name="fk_scientific_return_watch_snapshot",
        ),
        sa.UniqueConstraint("project_id"),
        sa.UniqueConstraint("project_snapshot_id"),
    )
    op.create_index(
        "ix_scientific_return_watches_project_id",
        "scientific_return_watches",
        ["project_id"],
        unique=True,
    )
    op.create_index(
        "ix_scientific_return_watches_created_by",
        "scientific_return_watches",
        ["created_by"],
    )
    op.create_index(
        "ix_scientific_return_watches_next_run_at",
        "scientific_return_watches",
        ["next_run_at"],
    )

    op.create_table(
        "scientific_return_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("watch_id", sa.String(length=36), nullable=False),
        sa.Column("status", run_status, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("candidate_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["watch_id"],
            ["scientific_return_watches.id"],
            name="fk_scientific_return_run_watch",
        ),
    )
    op.create_index(
        "ix_scientific_return_runs_watch_id",
        "scientific_return_runs",
        ["watch_id"],
    )
    op.create_index(
        "ix_scientific_return_runs_started_at",
        "scientific_return_runs",
        ["started_at"],
    )

    op.create_table(
        "scientific_return_queries",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("query_type", query_type, nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("result_count", sa.Integer(), nullable=False),
        sa.Column("status", query_status, nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["scientific_return_runs.id"],
            name="fk_scientific_return_query_run",
        ),
    )
    op.create_index(
        "ix_scientific_return_queries_run_id",
        "scientific_return_queries",
        ["run_id"],
    )

    op.create_table(
        "scientific_return_candidates",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("watch_id", sa.String(length=36), nullable=False),
        sa.Column("first_seen_run_id", sa.String(length=36), nullable=False),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("source_record_id", sa.String(length=255), nullable=False),
        sa.Column("deduplication_key", sa.String(length=255), nullable=False),
        sa.Column("doi", sa.String(length=255), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("authors", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("publication_date", sa.String(length=32), nullable=True),
        sa.Column("abstract", sa.Text(), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("raw_metadata_hash", sa.String(length=64), nullable=False),
        sa.Column("status", candidate_status, nullable=False),
        sa.Column("snoozed_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "confirmed_publication_entry_id", sa.String(length=36), nullable=True
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["watch_id"],
            ["scientific_return_watches.id"],
            name="fk_scientific_return_candidate_watch",
        ),
        sa.ForeignKeyConstraint(
            ["first_seen_run_id"],
            ["scientific_return_runs.id"],
            name="fk_scientific_return_candidate_run",
        ),
        sa.ForeignKeyConstraint(
            ["confirmed_publication_entry_id"],
            ["publication_log_entries.id"],
            name="fk_scientific_return_candidate_publication_entry",
        ),
        sa.UniqueConstraint(
            "watch_id",
            "deduplication_key",
            name="uq_scientific_return_candidate_key",
        ),
    )
    op.create_index(
        "ix_scientific_return_candidates_watch_id",
        "scientific_return_candidates",
        ["watch_id"],
    )
    op.create_index(
        "ix_scientific_return_candidates_first_seen_run_id",
        "scientific_return_candidates",
        ["first_seen_run_id"],
    )
    op.create_index(
        "ix_scientific_return_candidates_status",
        "scientific_return_candidates",
        ["status"],
    )
    op.create_index(
        "ix_scientific_return_candidates_created_at",
        "scientific_return_candidates",
        ["created_at"],
    )

    op.create_table(
        "scientific_return_evidences",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("candidate_id", sa.String(length=36), nullable=False),
        sa.Column("type", evidence_type, nullable=False),
        sa.Column("strength", evidence_strength, nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("source_field", sa.String(length=120), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["scientific_return_candidates.id"],
            name="fk_scientific_return_evidence_candidate",
        ),
    )
    op.create_index(
        "ix_scientific_return_evidences_candidate_id",
        "scientific_return_evidences",
        ["candidate_id"],
    )

    op.create_table(
        "scientific_return_decisions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("candidate_id", sa.String(length=36), nullable=False),
        sa.Column("decision", decision_type, nullable=False),
        sa.Column("justification", sa.Text(), nullable=True),
        sa.Column("decided_by", sa.String(length=36), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "evidence_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("correction", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["scientific_return_candidates.id"],
            name="fk_scientific_return_decision_candidate",
        ),
    )
    op.create_index(
        "ix_scientific_return_decisions_candidate_id",
        "scientific_return_decisions",
        ["candidate_id"],
    )
    op.create_index(
        "ix_scientific_return_decisions_decided_by",
        "scientific_return_decisions",
        ["decided_by"],
    )
    op.create_index(
        "ix_scientific_return_decisions_decided_at",
        "scientific_return_decisions",
        ["decided_at"],
    )


def downgrade() -> None:
    op.drop_table("scientific_return_decisions")
    op.drop_table("scientific_return_evidences")
    op.drop_table("scientific_return_candidates")
    op.drop_table("scientific_return_queries")
    op.drop_table("scientific_return_runs")
    op.drop_table("scientific_return_watches")
    op.drop_table("scientific_return_snapshots")

    for name in (
        "scientific_return_decision_type",
        "scientific_return_evidence_strength",
        "scientific_return_evidence_type",
        "scientific_return_candidate_status",
        "scientific_return_query_type",
        "scientific_return_query_status",
        "scientific_return_run_status",
        "scientific_return_watch_status",
    ):
        sa.Enum(name=name).drop(op.get_bind(), checkfirst=True)
