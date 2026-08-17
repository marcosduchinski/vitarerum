"""Add the agentic investigation cycle and evidence provenance

Additive only. The three new tables are empty until an investigation runs, and
the provenance columns on ``scientific_return_evidences`` are nullable, so every
evidence row written by the deterministic pipeline stays valid and readable.

Revision ID: 0064_scientific_return_inv
Revises: 0063_scientific_return_agent
Create Date: 2026-08-17
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# ``alembic_version.version_num`` is varchar(32), so the identifier is kept
# short rather than matching the file name.
revision: str = "0064_scientific_return_inv"
down_revision: str | None = "0063_scientific_return_agent"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_EVIDENCE_PROVENANCE: tuple[tuple[str, sa.types.TypeEngine[str]], ...] = (
    ("investigation_id", sa.String(length=36)),
    ("iteration_id", sa.String(length=80)),
    ("tool_execution_id", sa.String(length=36)),
    ("query_id", sa.String(length=36)),
    ("source_record_id", sa.String(length=255)),
    ("content_hash", sa.String(length=64)),
)


def _enum(name: str, *values: str) -> postgresql.ENUM:
    return postgresql.ENUM(*values, name=name, create_type=False)


def upgrade() -> None:
    objective = _enum(
        "scientific_return_investigation_objective",
        "DISCOVER_CANDIDATE",
        "ENRICH_CANDIDATE",
    )
    status = _enum(
        "scientific_return_investigation_status",
        "CREATED",
        "OBSERVING",
        "PLANNING",
        "VALIDATING",
        "EXECUTING",
        "REFLECTING",
        "AWAITING_HUMAN_REVIEW",
        "STOPPED",
        "FAILED",
    )
    mode = _enum(
        "scientific_return_investigation_mode",
        "DISABLED",
        "SHADOW",
        "POLICY_ONLY",
        "SUPERVISED",
        "SCHEDULED",
    )
    stop_reason = _enum(
        "scientific_return_stop_reason",
        "EVIDENCE_SUFFICIENT",
        "NO_RESULTS",
        "NO_EVIDENCE_ADDED",
        "NO_PROGRESS",
        "ACTION_REJECTED",
        "QUERY_REPEATED",
        "BUDGET_EXHAUSTED",
        "ITERATION_LIMIT_REACHED",
        "CANDIDATE_LIMIT_REACHED",
        "REASONER_UNAVAILABLE",
        "INVALID_PLAN",
        "TOOL_UNAVAILABLE",
        "TOOL_FAILED",
        "CANDIDATE_ALREADY_DECIDED",
        "PRESENTED_FOR_REVIEW",
        "INSUFFICIENT_EVIDENCE",
    )
    iteration_status = _enum(
        "scientific_return_iteration_status", "RUNNING", "COMPLETED", "FAILED"
    )
    rejection_reason = _enum(
        "scientific_return_policy_rejection_reason",
        "ACTION_NOT_ALLOWED",
        "SOURCE_NOT_ALLOWED",
        "OBJECT_NOT_IN_SNAPSHOT",
        "OBJECT_ID_REQUIRED",
        "INVENTORY_MISSING",
        "NO_NEW_QUERY_VARIANT",
        "BUDGET_EXHAUSTED",
        "ITERATION_LIMIT_REACHED",
        "CANDIDATE_LIMIT_REACHED",
        "CANDIDATE_ALREADY_DECIDED",
        "MODE_FORBIDS_EXECUTION",
        "INVESTIGATION_NOT_ACTIONABLE",
    )
    progress = _enum(
        "scientific_return_agent_progress",
        "CANDIDATE_CREATED",
        "EVIDENCE_ADDED",
        "NO_NEW_EVIDENCE",
        "NO_RESULTS",
        "FAILED",
    )
    recommended_action = _enum(
        "scientific_return_agent_recommended_action",
        "PRESENT_FOR_REVIEW",
        "SEARCH_INVENTORY_VARIANTS",
        "SEARCH_AUTHOR_VARIANTS",
        "SEARCH_TAXON_VARIANTS",
        "SEARCH_FULL_TEXT",
        "DEPRIORITIZE",
        "STOP_INSUFFICIENT_EVIDENCE",
    )
    for enum in (
        objective,
        status,
        mode,
        stop_reason,
        iteration_status,
        rejection_reason,
        progress,
    ):
        enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "scientific_return_agent_investigations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("watch_id", sa.String(length=36), nullable=False),
        sa.Column("candidate_id", sa.String(length=36), nullable=True),
        sa.Column("initial_run_id", sa.String(length=36), nullable=False),
        sa.Column("previous_investigation_id", sa.String(length=36), nullable=True),
        sa.Column("objective", objective, nullable=False),
        sa.Column("status", status, nullable=False),
        sa.Column("mode", mode, nullable=False),
        sa.Column("stop_reason", stop_reason, nullable=True),
        sa.Column("current_iteration", sa.Integer(), nullable=False, default=0),
        sa.Column("budget", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("contract_version", sa.String(length=96), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, default=0),
        sa.ForeignKeyConstraint(
            ["watch_id"],
            ["scientific_return_watches.id"],
            name="fk_scientific_return_investigation_watch",
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["scientific_return_candidates.id"],
            name="fk_scientific_return_investigation_candidate",
        ),
        sa.ForeignKeyConstraint(
            ["initial_run_id"],
            ["scientific_return_runs.id"],
            name="fk_scientific_return_investigation_run",
        ),
    )
    for column in (
        "watch_id",
        "candidate_id",
        "initial_run_id",
        "status",
        "started_at",
        "created_by",
    ):
        op.create_index(
            f"ix_scientific_return_agent_investigations_{column}",
            "scientific_return_agent_investigations",
            [column],
        )
    # At most one live investigation per watch, objective and candidate. The
    # partial index covers the NULL candidate of a discovery investigation,
    # which a plain unique constraint would not.
    op.execute(
        sa.text(
            "CREATE UNIQUE INDEX uq_scientific_return_investigation_live "
            "ON scientific_return_agent_investigations "
            "(watch_id, objective, COALESCE(candidate_id, '')) "
            "WHERE status NOT IN "
            "('AWAITING_HUMAN_REVIEW', 'STOPPED', 'FAILED')"
        )
    )

    op.create_table(
        "scientific_return_agent_iterations",
        sa.Column("id", sa.String(length=80), primary_key=True),
        sa.Column("investigation_id", sa.String(length=36), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("status", iteration_status, nullable=False),
        sa.Column("observation_payload", sa.Text(), nullable=True),
        sa.Column("plan_payload", sa.Text(), nullable=True),
        sa.Column("reflection_payload", sa.Text(), nullable=True),
        sa.Column("policy_authorized", sa.Boolean(), nullable=True),
        sa.Column("policy_rejection_reason", rejection_reason, nullable=True),
        sa.Column("policy_justification", sa.Text(), nullable=True),
        sa.Column("progress", progress, nullable=True),
        sa.Column("tool_execution_id", sa.String(length=36), nullable=True),
        sa.Column("evidence_before_hash", sa.String(length=64), nullable=True),
        sa.Column("evidence_after_hash", sa.String(length=64), nullable=True),
        sa.Column("evidence_delta", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["investigation_id"],
            ["scientific_return_agent_investigations.id"],
            name="fk_scientific_return_iteration_investigation",
        ),
        sa.UniqueConstraint(
            "investigation_id",
            "number",
            name="uq_scientific_return_agent_iteration_number",
        ),
    )
    op.create_index(
        "ix_scientific_return_agent_iterations_investigation_id",
        "scientific_return_agent_iterations",
        ["investigation_id"],
    )

    op.create_table(
        "scientific_return_agent_tool_executions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("investigation_id", sa.String(length=36), nullable=False),
        sa.Column("iteration_id", sa.String(length=80), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("action", recommended_action, nullable=False),
        sa.Column("queries_payload", sa.Text(), nullable=True),
        sa.Column("sources", sa.JSON(), nullable=True),
        sa.Column("total_results", sa.Integer(), nullable=False, default=0),
        sa.Column("created_candidate_ids", sa.JSON(), nullable=True),
        sa.Column("added_evidence_ids", sa.JSON(), nullable=True),
        sa.Column("result_hash", sa.String(length=64), nullable=True),
        sa.Column("succeeded", sa.Boolean(), nullable=False, default=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, default=1),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["investigation_id"],
            ["scientific_return_agent_investigations.id"],
            name="fk_scientific_return_tool_execution_investigation",
        ),
        sa.UniqueConstraint(
            "idempotency_key",
            name="uq_scientific_return_agent_tool_idempotency",
        ),
    )
    for column in ("investigation_id", "iteration_id"):
        op.create_index(
            f"ix_scientific_return_agent_tool_executions_{column}",
            "scientific_return_agent_tool_executions",
            [column],
        )

    for name, column_type in _EVIDENCE_PROVENANCE:
        op.add_column(
            "scientific_return_evidences",
            sa.Column(name, column_type, nullable=True),
        )
    op.create_index(
        "ix_scientific_return_evidences_investigation_id",
        "scientific_return_evidences",
        ["investigation_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_scientific_return_evidences_investigation_id",
        table_name="scientific_return_evidences",
    )
    for name, _ in reversed(_EVIDENCE_PROVENANCE):
        op.drop_column("scientific_return_evidences", name)

    op.drop_table("scientific_return_agent_tool_executions")
    op.drop_table("scientific_return_agent_iterations")
    op.execute(sa.text("DROP INDEX IF EXISTS uq_scientific_return_investigation_live"))
    op.drop_table("scientific_return_agent_investigations")

    bind = op.get_bind()
    # The recommended-action enum is shared with the shadow-analysis table and
    # is dropped by that migration, not this one.
    for name in (
        "scientific_return_agent_progress",
        "scientific_return_policy_rejection_reason",
        "scientific_return_iteration_status",
        "scientific_return_stop_reason",
        "scientific_return_investigation_mode",
        "scientific_return_investigation_status",
        "scientific_return_investigation_objective",
    ):
        postgresql.ENUM(name=name).drop(bind, checkfirst=True)
