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


class NarrativeData(BaseModel):
    narrative: str


class NarrativeResponse(BaseModel):
    narrative_id: str
    record_id: str
    status: str
    generated_at: datetime
    meta: NarrativeMeta
    data: NarrativeData


class StoredNarrativeResponse(BaseModel):
    narrative_id: str
    record_id: str
    generated_at: datetime
    meta: NarrativeMeta
    data: NarrativeData


class PaginatedNarrativesResponse(BaseModel):
    content: list[StoredNarrativeResponse]
    page: int
    size: int
    total_elements: int
    total_pages: int
