"""Restore the primary key on agentic investigation candidate links.

Revision ID: 0071_restore_agentic_link_pk
Revises: 0070_harden_full_agentic_prompts

Migration 0067 declared both a composite primary key and an identical named
unique constraint. PostgreSQL coalesced them into one primary-key constraint
named ``uq_sr_agentic_candidate_link``. Migration 0069 then dropped that
constraint by name, leaving the table without a conflict arbiter for the
repository's idempotent insert.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0071_restore_agentic_link_pk"
down_revision: str | None = "0070_harden_full_agentic_prompts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "sr_agentic_investigation_candidates"
_PRIMARY_KEY = "pk_sr_agentic_investigation_candidates"


def upgrade() -> None:
    op.create_primary_key(
        _PRIMARY_KEY,
        _TABLE,
        ("investigation_id", "candidate_id"),
    )


def downgrade() -> None:
    op.drop_constraint(_PRIMARY_KEY, _TABLE, type_="primary")
