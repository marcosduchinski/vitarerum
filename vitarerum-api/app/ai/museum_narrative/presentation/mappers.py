"""Domain → response mapping for the KG-RAG museum-narrative context.

Extracted from ``routes.py`` so the same mapping can be reused by the published
language (``app.ai.museum_narrative.public``) without pulling in the router.
"""

from __future__ import annotations

from app.ai.museum_narrative.domain.models import GeneratedNarrative
from app.ai.museum_narrative.presentation.schemas import (
    NarrativeData,
    NarrativeMeta,
    StoredNarrativeResponse,
)


def narrative_meta(record: GeneratedNarrative) -> NarrativeMeta:
    return NarrativeMeta(
        resolved_narrative_type=record.resolved_narrative_type.value,
        resolution_source=record.resolution_source.value,
        target_language=record.target_language,
        creativity_temperature=record.creativity_temperature,
        llm_model=record.llm_model,
    )


def stored_narrative_response(record: GeneratedNarrative) -> StoredNarrativeResponse:
    return StoredNarrativeResponse(
        narrative_id=record.id,
        record_id=record.record_id,
        generated_at=record.generated_at,
        meta=narrative_meta(record),
        data=NarrativeData(narrative=record.narrative),
    )
