"""Domain model for the KG-RAG museum-narrative context.

``narrative_type`` is a *rendering style* (the LLM persona), not a fact about the
visit: the same canonical facts are retold in different tones. When the caller
omits it, the pipeline defaults to ``INSTITUTIONAL``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import NewType

from app.ai.museum_narrative.domain.validation import NarrativeFinding
from app.shared.kernel import PermissionId

NarrativeId = NewType("NarrativeId", str)
NarrativeFactSnapshotId = NewType("NarrativeFactSnapshotId", str)
NarrativeRevisionId = NewType("NarrativeRevisionId", str)


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


@dataclass(frozen=True, slots=True)
class NarrativeFactSnapshot:
    """Immutable copy of the factual payload used for one narrative generation."""

    id: NarrativeFactSnapshotId
    record_id: str
    payload_json: str
    payload_hash: str
    builder_version: str
    prompt_version: str
    created_at: datetime
    cidoc_document_json: str | None = None
    cidoc_validation_report: str | None = None
    cidoc_conforms: bool | None = None

    @classmethod
    def create(
        cls,
        *,
        record_id: str,
        payload_json: str,
        payload_hash: str,
        builder_version: str,
        prompt_version: str,
        cidoc_document_json: str | None = None,
        cidoc_validation_report: str | None = None,
        cidoc_conforms: bool | None = None,
    ) -> NarrativeFactSnapshot:
        return cls(
            id=NarrativeFactSnapshotId(str(uuid.uuid4())),
            record_id=record_id,
            payload_json=payload_json,
            payload_hash=payload_hash,
            builder_version=builder_version,
            prompt_version=prompt_version,
            created_at=datetime.now(UTC),
            cidoc_document_json=cidoc_document_json,
            cidoc_validation_report=cidoc_validation_report,
            cidoc_conforms=cidoc_conforms,
        )


@dataclass(frozen=True, slots=True)
class GeneratedNarrativeRevision:
    """Append-only editorial revision preserving the previous narrative text."""

    id: NarrativeRevisionId
    narrative_id: NarrativeId
    previous_narrative: str
    revised_narrative: str
    created_at: datetime
    edited_by: PermissionId | None = None

    @classmethod
    def create(
        cls,
        *,
        narrative_id: NarrativeId,
        previous_narrative: str,
        revised_narrative: str,
        edited_by: PermissionId | None = None,
    ) -> GeneratedNarrativeRevision:
        return cls(
            id=NarrativeRevisionId(str(uuid.uuid4())),
            narrative_id=narrative_id,
            previous_narrative=previous_narrative,
            revised_narrative=revised_narrative,
            created_at=datetime.now(UTC),
            edited_by=edited_by,
        )


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
    facts_snapshot_id: NarrativeFactSnapshotId | None = None
    prompt_version_id: str | None = None
    prompt_version: str | None = None
    model_response_hash: str | None = None
    facts_snapshot: NarrativeFactSnapshot | None = None
    validation_conforms: bool | None = None
    validation_findings: list[NarrativeFinding] = field(default_factory=list)

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
        facts_snapshot_id: NarrativeFactSnapshotId | None = None,
        prompt_version_id: str | None = None,
        prompt_version: str | None = None,
        model_response_hash: str | None = None,
        facts_snapshot: NarrativeFactSnapshot | None = None,
        validation_conforms: bool | None = None,
        validation_findings: list[NarrativeFinding] | None = None,
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
            facts_snapshot_id=facts_snapshot_id,
            prompt_version_id=prompt_version_id,
            prompt_version=prompt_version,
            model_response_hash=model_response_hash,
            facts_snapshot=facts_snapshot,
            validation_conforms=validation_conforms,
            validation_findings=validation_findings or [],
        )

    def edit_narrative(
        self, narrative: str, edited_by: PermissionId
    ) -> GeneratedNarrativeRevision:
        """Replace the narrative text and return the append-only revision."""
        text = narrative.strip()
        if not text:
            raise ValueError("narrative must not be empty.")
        revision = GeneratedNarrativeRevision.create(
            narrative_id=self.id,
            previous_narrative=self.narrative,
            revised_narrative=text,
            edited_by=edited_by,
        )
        self.narrative = text
        return revision
