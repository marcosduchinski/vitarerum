"""Domain model for the KG-RAG museum-narrative context.

``narrative_type`` is a *rendering style* (the LLM persona), not a fact about the
visit: the same CIDOC-CRM graph is retold in different tones. When the caller
omits it, the pipeline defaults to ``INSTITUTIONAL``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import NewType

NarrativeId = NewType("NarrativeId", str)


class NarrativeType(StrEnum):
    INSTITUTIONAL = "institutional"
    SCIENTIFIC = "scientific"
    AUDIOGUIDE_ADULT = "audioguide_adult"
    AUDIOGUIDE_CHILD = "audioguide_child"
    SOCIAL_MEDIA = "social_media"


class ResolutionSource(StrEnum):
    REQUEST_BODY = "request_body"
    DEFAULT = "default"


DEFAULT_NARRATIVE_TYPE = NarrativeType.INSTITUTIONAL


@dataclass(slots=True)
class GeneratedNarrative:
    """A persisted narrative generation — one immutable row per run. The same
    in-situ visit (``record_id``) can be retold many times in different styles,
    languages, and creativity settings; each generation is kept as history."""

    id: NarrativeId
    record_id: str
    narrative: str
    resolved_narrative_type: NarrativeType
    resolution_source: ResolutionSource
    target_language: str
    creativity_temperature: float
    llm_model: str
    generated_at: datetime

    @classmethod
    def create(
        cls,
        *,
        record_id: str,
        narrative: str,
        resolved_narrative_type: NarrativeType,
        resolution_source: ResolutionSource,
        target_language: str,
        creativity_temperature: float,
        llm_model: str,
    ) -> GeneratedNarrative:
        """Build a fresh generation, assigning the id and stamping ``generated_at``."""
        return cls(
            id=NarrativeId(str(uuid.uuid4())),
            record_id=record_id,
            narrative=narrative,
            resolved_narrative_type=resolved_narrative_type,
            resolution_source=resolution_source,
            target_language=target_language,
            creativity_temperature=creativity_temperature,
            llm_model=llm_model,
            generated_at=datetime.now(UTC),
        )

    def edit_narrative(self, narrative: str) -> None:
        """Replace the narrative text (manual editorial correction)."""
        text = narrative.strip()
        if not text:
            raise ValueError("narrative must not be empty.")
        self.narrative = text
