"""Remove the Scientific Return test bench schema.

Revision ID: 0074_drop_sr_test_bench
Revises: 0073_full_agentic_degraded

The downgrade recreates the former schema but cannot restore deleted data.
Production rollout must archive required data and drain bench workers first.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0074_drop_sr_test_bench"
down_revision: str | None = "0073_full_agentic_degraded"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table in (
        "sr_test_candidates",
        "sr_test_search_attempts",
        "sr_test_items",
        "sr_test_batch_sources",
        "sr_test_batches",
        "sr_test_source_revisions",
        "sr_test_sources",
    ):
        op.drop_table(table)


def downgrade() -> None:
    op.create_table(
        "sr_test_sources",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("institution_id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("kind", sa.String(23), nullable=False),
        sa.Column("status", sa.String(7), nullable=False),
        sa.Column("current_revision", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("created_by", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "institution_id", "content_hash", name="uq_sr_test_source_content"
        ),
    )
    op.create_index(
        "ix_sr_test_sources_institution_id", "sr_test_sources", ["institution_id"]
    )
    op.create_index("ix_sr_test_sources_status", "sr_test_sources", ["status"])
    op.create_table(
        "sr_test_source_revisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "source_id",
            sa.String(36),
            sa.ForeignKey("sr_test_sources.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("locator", sa.String(2048)),
        sa.Column("authors_payload", sa.Text()),
        sa.Column("content_payload", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("created_by", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source_id", "revision", name="uq_sr_test_source_revision"),
    )
    op.create_index(
        "ix_sr_test_source_revisions_source_id",
        "sr_test_source_revisions",
        ["source_id"],
    )
    op.create_index(
        "ix_sr_test_source_revisions_content_hash",
        "sr_test_source_revisions",
        ["content_hash"],
    )
    op.create_table(
        "sr_test_batches",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("institution_id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(255)),
        sa.Column("description", sa.Text()),
        sa.Column("status", sa.String(21), nullable=False),
        sa.Column("idempotency_key", sa.String(128), unique=True),
        sa.Column(
            "cancellation_requested",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("created_by", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index(
        "ix_sr_test_batches_institution_id", "sr_test_batches", ["institution_id"]
    )
    op.create_index("ix_sr_test_batches_status", "sr_test_batches", ["status"])
    op.create_index("ix_sr_test_batches_created_by", "sr_test_batches", ["created_by"])
    op.create_table(
        "sr_test_batch_sources",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "batch_id",
            sa.String(36),
            sa.ForeignKey("sr_test_batches.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "source_id",
            sa.String(36),
            sa.ForeignKey("sr_test_sources.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "revision_id",
            sa.String(36),
            sa.ForeignKey("sr_test_source_revisions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("source_name", sa.String(255), nullable=False),
        sa.Column("source_revision", sa.Integer(), nullable=False),
        sa.Column("locator", sa.String(2048)),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.UniqueConstraint(
            "batch_id", "revision_id", name="uq_sr_test_batch_source_revision"
        ),
    )
    op.create_index(
        "ix_sr_test_batch_sources_batch_id", "sr_test_batch_sources", ["batch_id"]
    )
    op.create_table(
        "sr_test_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "batch_id",
            sa.String(36),
            sa.ForeignKey("sr_test_batches.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("author_payload", sa.Text(), nullable=False),
        sa.Column("object_name_payload", sa.Text(), nullable=False),
        sa.Column("inventory_number_payload", sa.Text(), nullable=False),
        sa.Column("subject_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(9), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("lease_owner", sa.String(128)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True)),
        sa.Column("error_code", sa.String(96)),
        sa.Column("error_message", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("batch_id", "ordinal", name="uq_sr_test_item_ordinal"),
    )
    op.create_index("ix_sr_test_items_batch_id", "sr_test_items", ["batch_id"])
    op.create_index("ix_sr_test_items_status", "sr_test_items", ["status"])
    op.create_index(
        "ix_sr_test_items_lease_expires_at", "sr_test_items", ["lease_expires_at"]
    )
    op.create_table(
        "sr_test_search_attempts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "item_id",
            sa.String(36),
            sa.ForeignKey("sr_test_items.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("item_attempt_number", sa.Integer(), nullable=False),
        sa.Column(
            "source_revision_id",
            sa.String(36),
            sa.ForeignKey("sr_test_source_revisions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("query_payload", sa.Text(), nullable=False),
        sa.Column("query_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(9), nullable=False),
        sa.Column("result_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("model", sa.String(128)),
        sa.Column("prompt_version_id", sa.String(36)),
        sa.Column("prompt_version", sa.String(96)),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint(
            "item_id",
            "item_attempt_number",
            "source_revision_id",
            "query_hash",
            name="uq_sr_test_search_attempt",
        ),
    )
    op.create_index(
        "ix_sr_test_search_attempts_item_id", "sr_test_search_attempts", ["item_id"]
    )
    op.create_table(
        "sr_test_candidates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "attempt_id",
            sa.String(36),
            sa.ForeignKey("sr_test_search_attempts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("score", sa.Numeric(6, 5), nullable=False),
        sa.Column("score_version", sa.String(96), nullable=False),
        sa.Column("discovery_basis", sa.String(96), nullable=False),
        sa.Column("inventory_evidence_status", sa.String(12), nullable=False),
        sa.Column("evidence_payload", sa.Text()),
        sa.Column("evidence_start", sa.Integer()),
        sa.Column("evidence_end", sa.Integer()),
        sa.Column("source_field", sa.String(120)),
        sa.CheckConstraint("score >= 0 AND score <= 1", name="ck_sr_test_score_range"),
        sa.UniqueConstraint("attempt_id", "rank", name="uq_sr_test_candidate_rank"),
    )
    op.create_index(
        "ix_sr_test_candidates_attempt_id", "sr_test_candidates", ["attempt_id"]
    )


