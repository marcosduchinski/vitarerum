"""Pydantic request/response shapes for the in-situ visit report endpoint,
matching 10Reports-InSituVisit.md."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from app.ai.museum_narrative.presentation.schemas import StoredNarrativeResponse
from app.cidoc_crm.in_situ_visit_mapping.presentation.schemas import (
    InSituVisitRecordResponse,
)


class InSituVisitReportRequest(BaseModel):
    target_language: str = "pt"
    narrative_type: str | None = None
    creativity_temperature: float = Field(default=0.3, ge=0.0, le=1.0)


class InSituVisitReportResponse(BaseModel):
    id: str
    createdAt: datetime
    createdBy: str
    projectId: str
    narrativeId: str
    inSituVisitRecordId: str


class PaginatedInSituVisitReportsResponse(BaseModel):
    content: list[InSituVisitReportResponse]
    page: int
    size: int
    totalElements: int
    totalPages: int


class InSituVisitReportSummaryResponse(BaseModel):
    """A list row: the report's linkage ids plus a few human-readable fields
    (visit code, visitor, place, dates) read from its record, so a list/table
    renders without a per-row drill-down."""

    id: str
    createdAt: datetime
    createdBy: str
    projectId: str
    narrativeId: str
    inSituVisitRecordId: str
    code: str | None = None
    visitorName: str | None = None
    placeName: str | None = None
    visitBeginDate: date | None = None
    visitEndDate: date | None = None


class PaginatedInSituVisitReportSummariesResponse(BaseModel):
    content: list[InSituVisitReportSummaryResponse]
    page: int
    size: int
    totalElements: int
    totalPages: int


class InSituVisitReportDetailResponse(BaseModel):
    """The report plus its embedded narrative and in-situ visit record (with
    nested children and attachments), for the report detail page."""

    id: str
    createdAt: datetime
    createdBy: str
    projectId: str
    narrativeId: str
    inSituVisitRecordId: str
    narrative: StoredNarrativeResponse | None
    record: InSituVisitRecordResponse | None
