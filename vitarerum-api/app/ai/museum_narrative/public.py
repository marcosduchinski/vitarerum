"""Museum-narrative published language (Open Host Service).

The ONLY ``ai.museum_narrative`` module downstream contexts (e.g. the in-situ
visit report aggregator) may import — enforced by import-linter. Exposes reading
a stored narrative back as its presentation DTO. Mirrors the
``app.cidoc_crm.public`` pattern (lazy infra import).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.ai.museum_narrative.presentation.schemas import StoredNarrativeResponse

from app.ai.museum_narrative.domain.ports import (
    ModelTimeout,
    ModelUnavailable,
    RecordNotFound,
    SemanticValidationFailed,
    UnsupportedNarrativeType,
)


@dataclass(frozen=True, slots=True)
class NarrativeGenerationOptions:
    narrative_type: str | None = None
    target_language: str = "pt"
    creativity_temperature: float = 0.3


async def generate_narrative(
    session: AsyncSession, record_id: str, options: NarrativeGenerationOptions
) -> StoredNarrativeResponse:
    """Generate and persist a narrative for ``record_id`` using published DTOs.

    Raises this context's public error vocabulary unchanged for callers to map at
    their own boundary.
    """
    from app.ai.museum_narrative.application.use_cases import (
        GenerateNarrative,
        GenerateNarrativeInput,
    )
    from app.ai.museum_narrative.infrastructure.cidoc_acl import NarrativeFactsAdapter
    from app.ai.museum_narrative.infrastructure.model_ollama import (
        OllamaNarrativeAdapter,
    )
    from app.ai.museum_narrative.infrastructure.repositories import (
        SqlAlchemyNarrativeRepository,
    )
    from app.ai.museum_narrative.presentation.mappers import (
        stored_narrative_response,
    )
    from app.config import settings

    repository = SqlAlchemyNarrativeRepository(session)
    model = OllamaNarrativeAdapter(
        base_url=settings.ollama_base_url,
        model=settings.narrative_model,
        timeout_seconds=settings.narrative_timeout_seconds,
        api_key=settings.ollama_api_key,
    )
    use_case = GenerateNarrative(
        NarrativeFactsAdapter(session),
        model,
        repository,
        settings.narrative_model,
    )
    narrative = await use_case.execute(
        GenerateNarrativeInput(
            record_id=record_id,
            narrative_type=options.narrative_type,
            target_language=options.target_language,
            creativity_temperature=options.creativity_temperature,
        )
    )
    return stored_narrative_response(narrative)


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


__all__ = [
    "generate_narrative",
    "get_narrative_view",
    "ModelTimeout",
    "ModelUnavailable",
    "NarrativeGenerationOptions",
    "RecordNotFound",
    "SemanticValidationFailed",
    "UnsupportedNarrativeType",
]
