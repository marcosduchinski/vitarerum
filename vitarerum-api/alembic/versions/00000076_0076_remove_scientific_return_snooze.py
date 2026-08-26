"""Remove the scientific-return snooze decision.

Revision ID: 0076_remove_sr_snooze
Revises: 0075_remove_sr_shadow

Snooze hid a candidate from the default queue and promised to return it once
the date passed, but only one caller ever kept that promise: the deterministic
run, and only when it happened to re-find the same bibliographic record. A
candidate discovered by the full-agentic flow was never restored at all, so
snoozing it removed it from review indefinitely. Curators use PENDING as the
working queue instead.

Upgrade therefore returns every snoozed candidate to PENDING, which is where
they should have been once their date passed, and drops the column and the two
enum values.

Irreversible: historical SNOOZE rows in scientific_return_decisions are
deleted, because the enum value cannot be dropped while they reference it. A
snooze recorded no judgement about scientific return — it deferred one — and
the candidate it deferred returns to PENDING for a real decision. Downgrade
restores the schema, not those rows or the original snooze dates.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0076_remove_sr_snooze"
down_revision: str | None = "0075_remove_sr_shadow"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STATUS_ENUM = "scientific_return_candidate_status"
_DECISION_ENUM = "scientific_return_decision_type"

_STATUS_WITHOUT_SNOOZE = ("PENDING", "CONFIRMED", "DISMISSED")
_STATUS_WITH_SNOOZE = (*_STATUS_WITHOUT_SNOOZE, "SNOOZED")
_DECISION_WITHOUT_SNOOZE = ("CONFIRM", "CORRECT_AND_CONFIRM", "DISMISS")
_DECISION_WITH_SNOOZE = (*_DECISION_WITHOUT_SNOOZE, "SNOOZE")


def _replace_enum(
    name: str, values: tuple[str, ...], table: str, column: str
) -> None:
    """Rebuild a Postgres enum with a different value set.

    Postgres cannot drop a value from an enum, so the type is recreated and the
    column re-pointed at it. Every row must already hold a value present in
    ``values`` or the cast fails, which is the intended safety net.
    """
    old = f"{name}_old"
    op.execute(sa.text(f"ALTER TYPE {name} RENAME TO {old}"))
    op.execute(
        sa.text(
            f"CREATE TYPE {name} AS ENUM ("
            + ", ".join(f"'{value}'" for value in values)
            + ")"
        )
    )
    op.execute(
        sa.text(
            f"ALTER TABLE {table} ALTER COLUMN {column} "
            f"TYPE {name} USING {column}::text::{name}"
        )
    )
    op.execute(sa.text(f"DROP TYPE {old}"))


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE scientific_return_candidates "
            "SET status = 'PENDING', snoozed_until = NULL "
            "WHERE status = 'SNOOZED'"
        )
    )
    op.execute(
        sa.text("DELETE FROM scientific_return_decisions WHERE decision = 'SNOOZE'")
    )
    op.drop_column("scientific_return_candidates", "snoozed_until")
    _replace_enum(
        _STATUS_ENUM,
        _STATUS_WITHOUT_SNOOZE,
        "scientific_return_candidates",
        "status",
    )
    _replace_enum(
        _DECISION_ENUM,
        _DECISION_WITHOUT_SNOOZE,
        "scientific_return_decisions",
        "decision",
    )


def downgrade() -> None:
    _replace_enum(
        _STATUS_ENUM, _STATUS_WITH_SNOOZE, "scientific_return_candidates", "status"
    )
    _replace_enum(
        _DECISION_ENUM,
        _DECISION_WITH_SNOOZE,
        "scientific_return_decisions",
        "decision",
    )
    op.add_column(
        "scientific_return_candidates",
        sa.Column("snoozed_until", sa.DateTime(timezone=True), nullable=True),
    )
