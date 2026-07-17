"""Pydantic request/response shapes for the KG-RAG narrative endpoint,
matching 09KG-RAG-Narrative.md (camelCase JSON not required — the spec uses
snake_case keys)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class NarrativeRequest(BaseModel):
    target_language: str = "pt"
    narrative_type: str | None = None
    creativity_temperature: float = Field(default=0.3, ge=0.0, le=1.0)


class UpdateNarrativeRequest(BaseModel):
    narrative: str = Field(min_length=1)

    @field_validator("narrative")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        # Reject whitespace-only text at the boundary (422) and hand the domain a
        # trimmed value, so the non-empty invariant is never violated downstream.
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("narrative must not be blank")
        return trimmed


class NarrativeMeta(BaseModel):
    resolved_narrative_type: str
    resolution_source: str
    target_language: str
    creativity_temperature: float
    llm_model: str
    facts_snapshot_id: str | None = None
    prompt_version: str | None = None
    model_response_hash: str | None = None
    validation_conforms: bool | None = None
    validation_findings: list[dict[str, str]] = Field(default_factory=list)


class NarrativeData(BaseModel):
    narrative: str


class NarrativeFactSnapshotResponse(BaseModel):
    id: str
    record_id: str
    payload_json: str
    payload_hash: str
    builder_version: str
    prompt_version: str
    created_at: datetime


class NarrativeResponse(BaseModel):
    narrative_id: str
    record_id: str
    status: str
    generated_at: datetime
    meta: NarrativeMeta
    data: NarrativeData
    facts_snapshot: NarrativeFactSnapshotResponse | None = None


class StoredNarrativeResponse(BaseModel):
    narrative_id: str
    record_id: str
    generated_at: datetime
    meta: NarrativeMeta
    data: NarrativeData
    facts_snapshot: NarrativeFactSnapshotResponse | None = None


class PaginatedNarrativesResponse(BaseModel):
    content: list[StoredNarrativeResponse]
    page: int
    size: int
    total_elements: int
    total_pages: int
