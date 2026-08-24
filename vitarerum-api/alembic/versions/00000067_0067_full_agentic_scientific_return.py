"""Add curator memory and the full-agentic scientific-return flow.

Revision ID: 0067_full_agentic_return
Revises: 0066_scientific_return_telemetry
Create Date: 2026-08-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0067_full_agentic_return"
down_revision: str | None = "0066_scientific_return_telemetry"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE scientific_return_query_type ADD VALUE IF NOT EXISTS 'AGENTIC'"
    )
    op.add_column(
        "scientific_return_runs",
        sa.Column(
            "run_kind",
            sa.String(length=32),
            nullable=False,
            server_default="DETERMINISTIC",
        ),
    )
    op.create_table(
        "sr_source_throttles",
        sa.Column("source", sa.String(80), primary_key=True),
        sa.Column("next_allowed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_sr_runs_kind", "scientific_return_runs", ["run_kind"])
    op.add_column(
        "scientific_return_decisions",
        sa.Column("decision_context_encrypted", sa.Text(), nullable=True),
    )

    op.create_table(
        "sr_knowledge_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("institution_id", sa.String(36), nullable=True),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("content_encrypted", sa.Text(), nullable=False),
        sa.Column("registered_number_encrypted", sa.Text(), nullable=True),
        sa.Column("registered_number_hash", sa.String(64), nullable=True),
        sa.Column("observed_form_encrypted", sa.Text(), nullable=True),
        sa.Column("observed_form_hash", sa.String(64), nullable=True),
        sa.Column("source_candidate_id", sa.String(36), nullable=True),
        sa.Column("source_decision_id", sa.String(36), nullable=True),
        sa.Column("supersedes_id", sa.String(36), nullable=True),
        sa.Column("proposed_by_model", sa.String(128), nullable=True),
        sa.Column("prompt_version", sa.String(96), nullable=True),
        sa.Column("created_by", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("validated_by", sa.String(36), nullable=True),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retired_by", sa.String(36), nullable=True),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["source_candidate_id"],
            ["scientific_return_candidates.id"],
            name="fk_sr_knowledge_candidate",
        ),
        sa.ForeignKeyConstraint(
            ["source_decision_id"],
            ["scientific_return_decisions.id"],
            name="fk_sr_knowledge_decision",
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_id"],
            ["sr_knowledge_items.id"],
            name="fk_sr_knowledge_supersedes",
        ),
    )
    op.create_index("ix_sr_knowledge_status", "sr_knowledge_items", ["status"])
    op.create_index("ix_sr_knowledge_created", "sr_knowledge_items", ["created_at"])
    op.create_index(
        "ix_sr_knowledge_registered",
        "sr_knowledge_items",
        ["institution_id", "registered_number_hash"],
    )

    op.create_table(
        "sr_full_agentic_investigations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("watch_id", sa.String(36), nullable=False),
        sa.Column("objective", sa.String(32), nullable=False),
        sa.Column("candidate_id", sa.String(36), nullable=True),
        sa.Column("search_run_id", sa.String(36), nullable=True, unique=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False, unique=True),
        sa.Column("budget", postgresql.JSONB(), nullable=False),
        sa.Column("usage", postgresql.JSONB(), nullable=False),
        sa.Column("created_by", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("cancel_requested_by", sa.String(36), nullable=True),
        sa.Column("lease_owner", sa.String(128), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(
            ["watch_id"], ["scientific_return_watches.id"], name="fk_sr_fa_watch"
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["scientific_return_candidates.id"],
            name="fk_sr_fa_candidate",
        ),
        sa.ForeignKeyConstraint(
            ["search_run_id"], ["scientific_return_runs.id"], name="fk_sr_fa_run"
        ),
    )
    op.create_index("ix_sr_fa_watch", "sr_full_agentic_investigations", ["watch_id"])
    op.create_index("ix_sr_fa_status", "sr_full_agentic_investigations", ["status"])
    op.create_index(
        "ix_sr_fa_created", "sr_full_agentic_investigations", ["created_at"]
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_sr_fa_live_target "
        "ON sr_full_agentic_investigations "
        "(watch_id, objective, COALESCE(candidate_id, '')) "
        "WHERE status IN ('QUEUED','RUNNING','CANCEL_REQUESTED')"
    )

    op.create_table(
        "sr_agentic_trajectory_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("investigation_id", sa.String(36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("payload_encrypted", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["investigation_id"],
            ["sr_full_agentic_investigations.id"],
            name="fk_sr_event_investigation",
        ),
        sa.UniqueConstraint(
            "investigation_id", "sequence", name="uq_sr_agentic_event_sequence"
        ),
    )
    op.create_index(
        "ix_sr_event_investigation",
        "sr_agentic_trajectory_events",
        ["investigation_id"],
    )

    op.create_table(
        "sr_agentic_knowledge_usage",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("investigation_id", sa.String(36), nullable=False),
        sa.Column("knowledge_item_id", sa.String(36), nullable=False),
        sa.Column("prompt_step", sa.String(64), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["investigation_id"],
            ["sr_full_agentic_investigations.id"],
            name="fk_sr_usage_investigation",
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_item_id"],
            ["sr_knowledge_items.id"],
            name="fk_sr_usage_knowledge",
        ),
        sa.UniqueConstraint(
            "investigation_id",
            "knowledge_item_id",
            "prompt_step",
            name="uq_sr_agentic_knowledge_usage",
        ),
    )
    op.create_index(
        "ix_sr_usage_investigation", "sr_agentic_knowledge_usage", ["investigation_id"]
    )
    op.create_index(
        "ix_sr_usage_knowledge", "sr_agentic_knowledge_usage", ["knowledge_item_id"]
    )

    op.create_table(
        "sr_agentic_investigation_candidates",
        sa.Column("investigation_id", sa.String(36), primary_key=True),
        sa.Column("candidate_id", sa.String(36), primary_key=True),
        sa.Column("relation_kind", sa.String(16), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["investigation_id"],
            ["sr_full_agentic_investigations.id"],
            name="fk_sr_link_investigation",
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["scientific_return_candidates.id"],
            name="fk_sr_link_candidate",
        ),
        sa.UniqueConstraint(
            "investigation_id", "candidate_id", name="uq_sr_agentic_candidate_link"
        ),
    )

    op.create_table(
        "sr_agentic_tool_executions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("investigation_id", sa.String(36), nullable=False),
        sa.Column("trajectory_sequence", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False, unique=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("invocation_encrypted", sa.Text(), nullable=False),
        sa.Column("result_encrypted", sa.Text(), nullable=True),
        sa.Column("result_hash", sa.String(64), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["investigation_id"],
            ["sr_full_agentic_investigations.id"],
            name="fk_sr_tool_investigation",
        ),
    )
    op.create_index(
        "ix_sr_tool_investigation", "sr_agentic_tool_executions", ["investigation_id"]
    )
    op.create_index("ix_sr_tool_status", "sr_agentic_tool_executions", ["status"])


def downgrade() -> None:
    op.drop_table("sr_agentic_tool_executions")
    op.drop_table("sr_agentic_investigation_candidates")
    op.drop_table("sr_agentic_knowledge_usage")
    op.drop_table("sr_agentic_trajectory_events")
    op.execute("DROP INDEX IF EXISTS uq_sr_fa_live_target")
    op.drop_table("sr_full_agentic_investigations")
    op.drop_table("sr_knowledge_items")
    op.drop_table("sr_source_throttles")
    op.drop_column("scientific_return_decisions", "decision_context_encrypted")
    op.drop_index("ix_sr_runs_kind", table_name="scientific_return_runs")
    op.drop_column("scientific_return_runs", "run_kind")
    # PostgreSQL enum values are intentionally not removed on downgrade.
