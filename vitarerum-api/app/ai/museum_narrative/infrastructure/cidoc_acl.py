"""Anti-corruption adapter over the CIDOC-CRM published language.

Implements ``CidocGraphPort`` by calling ``app.cidoc_crm.public``: builds the
JSON-LD for a record, expands + validates it, and translates the outcomes into
this context's error vocabulary.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.museum_narrative.domain.ports import (
    RecordNotFound,
    SemanticValidationFailed,
)
from app.cidoc_crm.public import (
    build_in_situ_visit_cidoc,
    expand_and_validate_cidoc,
)


class CidocGraphAdapter:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def prepare(self, record_id: str) -> dict[str, Any]:
        doc = await build_in_situ_visit_cidoc(self._session, record_id)
        if doc is None:
            raise RecordNotFound(f"No in-situ visit record found with id {record_id}")
        expanded, conforms, report = expand_and_validate_cidoc(doc)
        if not conforms:
            raise SemanticValidationFailed(report)
        return expanded
