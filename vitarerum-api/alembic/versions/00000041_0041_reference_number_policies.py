"""Add reference number policies

Revision ID: 0041_reference_number_policies
Revises: 0040_proposal_submission_channel
Create Date: 2026-07-23
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

revision: str = "0041_reference_number_policies"
down_revision: str | None = "0040_proposal_submission_channel"
branch_labels: str | None = None
depends_on: str | None = None

CREATED_AT = datetime(2026, 7, 23, tzinfo=UTC)


def upgrade() -> None:
    op.create_table(
        "reference_policies",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("mask", sa.String(length=128), nullable=False),
        sa.Column("sequence_scope", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("active_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("active_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.String(length=128), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("activated_by", sa.String(length=128), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_reference_policies_kind", "reference_policies", ["kind"])
    op.create_index(
        "ix_reference_policies_sequence_scope",
        "reference_policies",
        ["sequence_scope"],
    )
    op.create_index("ix_reference_policies_status", "reference_policies", ["status"])
    op.create_index(
        "ix_reference_policies_created_at", "reference_policies", ["created_at"]
    )

    op.create_table(
        "reference_legacy_formats",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=96), nullable=False),
        sa.Column("pattern", sa.String(length=160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "kind", "pattern", name="uq_reference_legacy_formats_kind_pattern"
        ),
    )
    op.create_index(
        "ix_reference_legacy_formats_kind", "reference_legacy_formats", ["kind"]
    )
    op.create_index(
        "ix_reference_legacy_formats_created_at",
        "reference_legacy_formats",
        ["created_at"],
    )

    op.create_table(
        "reference_policy_sequences",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("policy_id", sa.String(length=36), nullable=False),
        sa.Column("scope_key", sa.String(length=32), nullable=False),
        sa.Column("next_value", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["policy_id"], ["reference_policies.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "policy_id", "scope_key", name="uq_reference_policy_sequences_scope"
        ),
    )
    op.create_index(
        "ix_reference_policy_sequences_policy_id",
        "reference_policy_sequences",
        ["policy_id"],
    )

    op.create_table(
        "reference_policy_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("policy_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("actor_permission_id", sa.String(length=128), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["policy_id"], ["reference_policies.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_reference_policy_events_policy_id",
        "reference_policy_events",
        ["policy_id"],
    )
    op.create_index(
        "ix_reference_policy_events_event_type",
        "reference_policy_events",
        ["event_type"],
    )
    op.create_index(
        "ix_reference_policy_events_actor_permission_id",
        "reference_policy_events",
        ["actor_permission_id"],
    )
    op.create_index(
        "ix_reference_policy_events_occurred_at",
        "reference_policy_events",
        ["occurred_at"],
    )

    op.alter_column(
        "collection_use_projects",
        "reference_number",
        existing_type=sa.String(length=12),
        type_=sa.String(length=64),
        existing_nullable=False,
    )
    op.alter_column(
        "proposals",
        "reference_number",
        existing_type=sa.String(length=17),
        type_=sa.String(length=64),
        existing_nullable=False,
    )

    _seed_policies()
    _seed_legacy_formats()
    _seed_sequences()


def downgrade() -> None:
    op.alter_column(
        "proposals",
        "reference_number",
        existing_type=sa.String(length=64),
        type_=sa.String(length=17),
        existing_nullable=False,
    )
    op.alter_column(
        "collection_use_projects",
        "reference_number",
        existing_type=sa.String(length=64),
        type_=sa.String(length=12),
        existing_nullable=False,
    )
    op.drop_table("reference_policy_events")
    op.drop_table("reference_policy_sequences")
    op.drop_table("reference_legacy_formats")
    op.drop_table("reference_policies")


def _seed_policies() -> None:
    policies = [
        (
            "ref-pol-proposal-muhnac-v1",
            "PROPOSAL",
            "PP-MUHNAC/COL/YYYY/XXXX",
            "YEAR",
        ),
        (
            "ref-pol-project-muhnac-v1",
            "COLLECTION_USE_PROJECT",
            "PR-MUHNAC/COL/YYYY/XXXX",
            "YEAR",
        ),
        (
            "ref-pol-ol-muhnac-v1",
            "OBJECT_ACCESS_LOG",
            "OL-MUHNAC/COL/YYYY/XXXX",
            "YEAR",
        ),
        (
            "ref-pol-oo-muhnac-v1",
            "OBJECT_OCCURRENCE_LOG",
            "OO-MUHNAC/COL/YYYY/XXXX",
            "YEAR",
        ),
        (
            "ref-pol-op-muhnac-v1",
            "PUBLICATION_LOG",
            "OP-MUHNAC/COL/YYYY/XXXX",
            "YEAR",
        ),
    ]
    op.bulk_insert(
        sa.table(
            "reference_policies",
            sa.column("id", sa.String),
            sa.column("kind", sa.String),
            sa.column("mask", sa.String),
            sa.column("sequence_scope", sa.String),
            sa.column("status", sa.String),
            sa.column("active_from", sa.DateTime(timezone=True)),
            sa.column("active_until", sa.DateTime(timezone=True)),
            sa.column("created_by", sa.String),
            sa.column("created_at", sa.DateTime(timezone=True)),
            sa.column("updated_by", sa.String),
            sa.column("updated_at", sa.DateTime(timezone=True)),
            sa.column("activated_by", sa.String),
            sa.column("activated_at", sa.DateTime(timezone=True)),
        ),
        [
            {
                "id": policy_id,
                "kind": kind,
                "mask": mask,
                "sequence_scope": scope,
                "status": "ACTIVE",
                "active_from": CREATED_AT,
                "active_until": None,
                "created_by": "system",
                "created_at": CREATED_AT,
                "updated_by": "system",
                "updated_at": CREATED_AT,
                "activated_by": "system",
                "activated_at": CREATED_AT,
            }
            for policy_id, kind, mask, scope in policies
        ],
    )


def _seed_sequences() -> None:
    bind = op.get_bind()
    rows: list[dict[str, object]] = []

    for table_name, policy_id, prefix in [
        ("proposals", "ref-pol-proposal-muhnac-v1", "PP"),
        ("collection_use_projects", "ref-pol-project-muhnac-v1", "PR"),
        (
            "object_access_logs",
            "ref-pol-ol-muhnac-v1",
            "OL",
        ),
        (
            "object_occurrence_logs",
            "ref-pol-oo-muhnac-v1",
            "OO",
        ),
        ("publication_logs", "ref-pol-op-muhnac-v1", "OP"),
    ]:
        sequences: dict[str, int] = {}
        for (reference_number,) in bind.execute(
            sa.text(f"SELECT reference_number FROM {table_name}")
        ):
            match = re.fullmatch(
                rf"{prefix}-MUHNAC/COL/(\d{{4}})/(\d{{4}})", reference_number
            )
            if match is not None:
                scope_key = match.group(1)
                sequences[scope_key] = max(
                    sequences.get(scope_key, 0), int(match.group(2))
                )
        for scope_key, max_sequence in sequences.items():
            rows.append(
                {
                    "policy_id": policy_id,
                    "scope_key": scope_key,
                    "next_value": max_sequence + 1,
                    "updated_at": CREATED_AT,
                }
            )

    if not rows:
        return
    op.bulk_insert(
        sa.table(
            "reference_policy_sequences",
            sa.column("policy_id", sa.String),
            sa.column("scope_key", sa.String),
            sa.column("next_value", sa.Integer),
            sa.column("updated_at", sa.DateTime(timezone=True)),
        ),
        rows,
    )


def _seed_legacy_formats() -> None:
    op.bulk_insert(
        sa.table(
            "reference_legacy_formats",
            sa.column("id", sa.String),
            sa.column("kind", sa.String),
            sa.column("name", sa.String),
            sa.column("pattern", sa.String),
            sa.column("created_at", sa.DateTime(timezone=True)),
        ),
        [
            {
                "id": "ref-leg-vrp-daily-v1",
                "kind": "PROPOSAL",
                "name": "legacy-vrp-daily",
                "pattern": r"^VRP-\d{8}-\d{4}$",
                "created_at": CREATED_AT,
            },
            {
                "id": "ref-leg-cup-hex-v1",
                "kind": "COLLECTION_USE_PROJECT",
                "name": "legacy-cup-alnum",
                "pattern": r"^CUP-[A-Z0-9]{8}$",
                "created_at": CREATED_AT,
            },
            {
                "id": "ref-leg-oal-hex-v1",
                "kind": "OBJECT_ACCESS_LOG",
                "name": "legacy-oal-alnum",
                "pattern": r"^OAL-[A-Z0-9]{8}$",
                "created_at": CREATED_AT,
            },
            {
                "id": "ref-leg-ool-hex-v1",
                "kind": "OBJECT_OCCURRENCE_LOG",
                "name": "legacy-ool-alnum",
                "pattern": r"^OOL-[A-Z0-9]{8}$",
                "created_at": CREATED_AT,
            },
            {
                "id": "ref-leg-pub-hex-v1",
                "kind": "PUBLICATION_LOG",
                "name": "legacy-pub-alnum",
                "pattern": r"^PUB-[A-Z0-9]{8}$",
                "created_at": CREATED_AT,
            },
        ],
    )
