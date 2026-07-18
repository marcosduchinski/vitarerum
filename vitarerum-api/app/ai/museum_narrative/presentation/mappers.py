"""Domain → response mapping for the KG-RAG museum-narrative context.

Extracted from ``routes.py`` so the same mapping can be reused by the published
language (``app.ai.museum_narrative.public``) without pulling in the router.
"""

from __future__ import annotations

from app.ai.museum_narrative.application.use_cases import PreviewNarrativeResult
from app.ai.museum_narrative.domain.models import (
    GeneratedNarrative,
    GeneratedNarrativeRevision,
)
from app.ai.museum_narrative.presentation.schemas import (
    NarrativeData,
    NarrativeFactSnapshotResponse,
    NarrativeMeta,
    NarrativePreviewMeta,
    NarrativeRevisionResponse,
    StoredNarrativeResponse,
)


def narrative_meta(record: GeneratedNarrative) -> NarrativeMeta:
    return NarrativeMeta(
        resolved_narrative_type=record.resolved_narrative_type.value,
        resolution_source=record.resolution_source.value,
        target_language=record.target_language,
        creativity_temperature=record.creativity_temperature,
        llm_model=record.llm_model,
        facts_snapshot_id=record.facts_snapshot_id,
        prompt_version_id=record.prompt_version_id,
        prompt_version=record.prompt_version,
        model_response_hash=record.model_response_hash,
        validation_conforms=record.validation_conforms,
        validation_findings=[
            {
                "code": finding.code.value,
                "message": finding.message,
                "evidence": finding.evidence,
            }
            for finding in record.validation_findings
        ],
    )


def preview_narrative_meta(result: PreviewNarrativeResult) -> NarrativePreviewMeta:
    return NarrativePreviewMeta(
        resolved_narrative_type=result.resolved_narrative_type.value,
        resolution_source=result.resolution_source.value,
        target_language=result.target_language,
        creativity_temperature=result.creativity_temperature,
        llm_model=result.llm_model,
        facts_snapshot_id=None,
        prompt_version_id=result.prompt_version_id,
        prompt_version=result.prompt_version,
        prompt_status=result.prompt_status,
        model_response_hash=result.model_response_hash,
        validation_conforms=result.validation_conforms,
        validation_findings=[
            {
                "code": finding.code.value,
                "message": finding.message,
                "evidence": finding.evidence,
            }
            for finding in result.validation_findings
        ],
    )


def fact_snapshot_response(
    record: GeneratedNarrative,
) -> NarrativeFactSnapshotResponse | None:
    snapshot = record.facts_snapshot
    if snapshot is None:
        return None
    return NarrativeFactSnapshotResponse(
        id=snapshot.id,
        record_id=snapshot.record_id,
        payload_json=snapshot.payload_json,
        payload_hash=snapshot.payload_hash,
        builder_version=snapshot.builder_version,
        prompt_version=snapshot.prompt_version,
        created_at=snapshot.created_at,
        cidoc_document_json=snapshot.cidoc_document_json,
        cidoc_validation_report=snapshot.cidoc_validation_report,
        cidoc_conforms=snapshot.cidoc_conforms,
    )


def stored_narrative_response(record: GeneratedNarrative) -> StoredNarrativeResponse:
    return StoredNarrativeResponse(
        narrative_id=record.id,
        record_id=record.record_id,
        generated_at=record.generated_at,
        meta=narrative_meta(record),
        data=NarrativeData(narrative=record.narrative),
        facts_snapshot=fact_snapshot_response(record),
    )


def narrative_revision_response(
    revision: GeneratedNarrativeRevision,
) -> NarrativeRevisionResponse:
    return NarrativeRevisionResponse(
        id=revision.id,
        narrative_id=revision.narrative_id,
        previous_narrative=revision.previous_narrative,
        revised_narrative=revision.revised_narrative,
        created_at=revision.created_at,
        edited_by=revision.edited_by,
    )
