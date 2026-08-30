"""Make the consulted object part of what an investigation targets.

Revision ID: 0081_full_agentic_object
Revises: 0080_planner_prompt_v3

A project may consult several objects, and until now one investigation covered
them all from a single shared budget. The floor could not: it spends at most
half the query budget and a consulted object now costs four floor queries, so
the guaranteed attempts reached the first object, half of the second, and none
of the rest — the guarantee existed for object one only.

Giving each object its own investigation restores it, and does so without
re-deriving a single ceiling: the budgets were measured against one object and
stay valid for one object. The alternative — scaling every limit by the object
count — would replace measured numbers with formulas nobody has tested.

The live-target index moves with it. It exists so that one target cannot have
two live investigations at once, and the target is now the object rather than
the project. Existing rows keep a null object and behave exactly as before,
which is what the COALESCE preserves.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0081_full_agentic_object"
down_revision: str | None = "0080_planner_prompt_v3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "sr_full_agentic_investigations"


def upgrade() -> None:
    # Plain text, not a foreign key into use_of_collections: the snapshot
    # already carries the object identifier that way, and scientific return is
    # not allowed to depend on that context directly.
    op.add_column(_TABLE, sa.Column("object_id", sa.String(36), nullable=True))
    op.create_index("ix_sr_fa_object", _TABLE, ["object_id"])
    op.execute("DROP INDEX IF EXISTS uq_sr_fa_live_target")
    op.execute(
        "CREATE UNIQUE INDEX uq_sr_fa_live_target "
        f"ON {_TABLE} "
        "(watch_id, objective, COALESCE(candidate_id, ''), COALESCE(object_id, '')) "
        "WHERE status IN ('QUEUED','RUNNING','CANCEL_REQUESTED')"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_sr_fa_live_target")
    # Two live investigations of the same project would violate the narrower
    # index, so the rows that only differ by object have to go first.
    op.execute(
        f"DELETE FROM {_TABLE} a USING {_TABLE} b "
        "WHERE a.status IN ('QUEUED','RUNNING','CANCEL_REQUESTED') "
        "AND b.status IN ('QUEUED','RUNNING','CANCEL_REQUESTED') "
        "AND a.watch_id = b.watch_id AND a.objective = b.objective "
        "AND COALESCE(a.candidate_id, '') = COALESCE(b.candidate_id, '') "
        "AND a.created_at > b.created_at"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_sr_fa_live_target "
        f"ON {_TABLE} "
        "(watch_id, objective, COALESCE(candidate_id, '')) "
        "WHERE status IN ('QUEUED','RUNNING','CANCEL_REQUESTED')"
    )
    op.drop_index("ix_sr_fa_object", table_name=_TABLE)
    op.drop_column(_TABLE, "object_id")
