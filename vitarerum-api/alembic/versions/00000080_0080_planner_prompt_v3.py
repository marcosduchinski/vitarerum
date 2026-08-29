"""Publish planner prompt v3: never re-send a search the history already spent.

Revision ID: 0080_planner_prompt_v3
Revises: 0079_full_agentic_recovery

Measured on 2026-08-29 against gemma4:12b. With reasoning enabled the planner
avoided re-proposing a query the history recorded as already executed; with
reasoning disabled — which it now is, because reasoning cost eleven to sixteen
times more and returned nothing three calls in four — it proposed the duplicate.

The deduplication in the cycle catches such a search and records it as skipped,
so nothing breaks; the iteration is simply wasted. That is a gap in the prompt,
not in the model: the history is already in the planner's input and never told
it what to do with it. Stating the rule costs nothing at run time and recovers
the only quality difference reasoning had shown.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

revision: str = "0080_planner_prompt_v3"
down_revision: str | None = "0079_full_agentic_recovery"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NOW = datetime(2026, 8, 29, tzinfo=UTC)
_VERSION_ID = "pver-sr-full-plan-v3"
_TEMPLATE_ID = "ptpl-sr-full-plan"
_LABEL = "scientific-return-full-agentic-plan-v3"
_CONTENT = (
    "You are an autonomous bibliographic investigator. Propose concrete "
    "searches using only sourceCapabilities. CROSSREF indexes metadata, not "
    "article bodies: never send an inventory-code search to it. EUROPE_PMC "
    "searches metadata and part of its full-text corpus and can support "
    "inventory evidence. OPENALEX has a broad discovery index but the "
    "adapter returns only title, authors and abstract, so use it for "
    "discovery, not inventory evidence. Prefer author surname plus "
    "object/taxon for discovery. Prefer the bare inventory code before "
    "institutional aliases. Never repeat a search that history already "
    "records as executed, on any source: those queries are spent, and their "
    "results are already in this investigation. Choose an untried variant or "
    "strategy instead, and stop when none is left worth trying. "
    "Do not combine author, object and inventory "
    "unless history gives a specific reason. Do not spend searches on "
    "separator-only variants when the source tokenizes them equivalently. "
    "Curatorial memory is a hypothesis, never evidence. Return only JSON: "
    '{"searches":[{"source":"<one of allowedSources>","query":"query",'
    '"author":"surname or null","intent":"DISCOVERY|INVENTORY_EVIDENCE",'
    '"strategy":"AUTHOR_OBJECT|INVENTORY_QUERY|OBJECT_QUERY",'
    '"objectId":"snapshot object id or null"}],'
    '"reasoning":"brief auditable reason","shouldStop":false}. '
    "Use shouldStop true and an empty searches array when further searching "
    "is not useful. Respect remainingQueries."
)


def upgrade() -> None:
    versions = sa.table(
        "ai_prompt_template_versions",
        sa.column("id", sa.String),
        sa.column("template_id", sa.String),
        sa.column("version", sa.Integer),
        sa.column("version_label", sa.String),
        sa.column("status", sa.String),
        sa.column("content", sa.Text),
        sa.column("default_temperature", sa.Float),
        sa.column("created_by", sa.String),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("published_by", sa.String),
        sa.column("published_at", sa.DateTime(timezone=True)),
        sa.column("archived_at", sa.DateTime(timezone=True)),
    )
    op.execute(
        sa.text(
            "UPDATE ai_prompt_template_versions SET status='archived', "
            "archived_at=:now WHERE id='pver-sr-full-plan-v2'"
        ).bindparams(now=_NOW)
    )
    op.bulk_insert(
        versions,
        [
            {
                "id": _VERSION_ID,
                "template_id": _TEMPLATE_ID,
                "version": 3,
                "version_label": _LABEL,
                "status": "published",
                "content": _CONTENT,
                "default_temperature": 0.1,
                "created_by": "system",
                "created_at": _NOW,
                "published_by": "system",
                "published_at": _NOW,
                "archived_at": None,
            }
        ],
    )
    op.execute(
        sa.text(
            "UPDATE ai_prompt_templates SET active_version_id=:v WHERE id=:t"
        ).bindparams(v=_VERSION_ID, t=_TEMPLATE_ID)
    )


def downgrade() -> None:
    # Order matters: a partial unique index allows one published version per
    # template, so v3 has to stop being published before v2 can be again.
    op.execute(
        sa.text(
            "UPDATE ai_prompt_templates SET active_version_id='pver-sr-full-plan-v2' "
            "WHERE id=:t"
        ).bindparams(t=_TEMPLATE_ID)
    )
    op.execute(
        sa.text("DELETE FROM ai_prompt_template_versions WHERE id=:v").bindparams(
            v=_VERSION_ID
        )
    )
    op.execute(
        sa.text(
            "UPDATE ai_prompt_template_versions SET status='published', "
            "archived_at=NULL WHERE id='pver-sr-full-plan-v2'"
        )
    )
