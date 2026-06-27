"""Museum-narrative published language (Open Host Service).

The ONLY ``ai.museum_narrative`` module downstream contexts (e.g. the in-situ
visit report aggregator) may import — enforced by import-linter. Exposes reading
a stored narrative back as its presentation DTO. Mirrors the
``app.cidoc_crm.public`` pattern (lazy infra import).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.ai.museum_narrative.presentation.schemas import StoredNarrativeResponse


async def get_narrative_view(
    session: AsyncSession, record_id: str, narrative_id: str
) -> StoredNarrativeResponse | None:
    """Return the presentation DTO for a stored narrative, or ``None`` if no
    narrative with ``narrative_id`` exists under ``record_id``."""
    from app.ai.museum_narrative.domain.models import NarrativeId
    from app.ai.museum_narrative.infrastructure.repositories import (
        SqlAlchemyNarrativeRepository,
    )
    from app.ai.museum_narrative.presentation.mappers import (
        stored_narrative_response,
    )

    repository = SqlAlchemyNarrativeRepository(session)
    record = await repository.get_by_id(NarrativeId(narrative_id))
    # The narrative must belong to the record in the path.
    if record is None or record.record_id != record_id:
        return None
    return stored_narrative_response(record)


__all__ = ["get_narrative_view"]
