"""Add reasoner telemetry and the client idempotency key

Additive only. Both are nullable, so every investigation written before this
migration stays readable: an older trajectory simply reports no telemetry.

Revision ID: 0066_scientific_return_telemetry
Revises: 0065_scientific_return_prompts
Create Date: 2026-08-17
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0066_scientific_return_telemetry"
down_revision: str | None = "0065_scientific_return_prompts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ITERATIONS = "scientific_return_agent_iterations"
_INVESTIGATIONS = "scientific_return_agent_investigations"

_TELEMETRY: tuple[tuple[str, sa.types.TypeEngine[object]], ...] = (
    ("model", sa.String(length=128)),
    ("prompt_version", sa.String(length=96)),
    ("plan_latency_ms", sa.Integer()),
    ("reflection_latency_ms", sa.Integer()),
    ("plan_response_hash", sa.String(length=64)),
    ("reflection_response_hash", sa.String(length=64)),
)


def upgrade() -> None:
    for name, column_type in _TELEMETRY:
        op.add_column(_ITERATIONS, sa.Column(name, column_type, nullable=True))

    op.add_column(
        _INVESTIGATIONS,
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
    )
    # Unique so a repeated command can only ever find one investigation, and
    # partial so the many rows without a client key do not collide.
    op.execute(
        sa.text(
            "CREATE UNIQUE INDEX uq_scientific_return_investigation_idempotency "
            f"ON {_INVESTIGATIONS} (idempotency_key) "
            "WHERE idempotency_key IS NOT NULL"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DROP INDEX IF EXISTS uq_scientific_return_investigation_idempotency"
        )
    )
    op.drop_column(_INVESTIGATIONS, "idempotency_key")
    for name, _ in reversed(_TELEMETRY):
        op.drop_column(_ITERATIONS, name)
