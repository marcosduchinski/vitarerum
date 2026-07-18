"""Pydantic request/response shapes for the in-situ visit report endpoint,
matching 10Reports-InSituVisit.md."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from app.ai.museum_narrative.presentation.schemas import (
    PaginatedNarrativeRevisionsResponse,
    StoredNarrativeResponse,
)
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


class InSituVisitAuditEvidenceResponse(BaseModel):
    recordId: str | None
    projectId: str
    code: str | None
    executionEvidenceType: str | None
    executionOccurredAt: datetime | None
    executionRecordedBy: str | None
    executionEvidenceGaps: list[str] = Field(default_factory=list)
    approvedAt: datetime | None
    approvedBy: str | None
    approvalNote: str | None


class InSituVisitAuditCidocResponse(BaseModel):
    documentJson: str | None
    mappingVersion: str | None
    crmVersion: str | None
    recordSchemaVersion: int | None
    conforms: bool | None
    validationReport: str | None


class InSituVisitAuditFactsResponse(BaseModel):
    snapshotId: str | None
    payloadJson: str | None
    payloadHash: str | None
    builderVersion: str | None
    promptVersion: str | None
    createdAt: datetime | None


class InSituVisitAuditGenerationResponse(BaseModel):
    narrativeId: str | None
    generatedAt: datetime | None
    narrativeType: str | None
    resolutionSource: str | None
    targetLanguage: str | None
    creativityTemperature: float | None
    llmModel: str | None
    promptVersionId: str | None
    promptVersion: str | None
    responseHash: str | None


class InSituVisitAuditValidationResponse(BaseModel):
    conforms: bool | None
    findings: list[dict[str, str]] = Field(default_factory=list)


class InSituVisitAuditTrailResponse(BaseModel):
    id: str
    createdAt: datetime
    createdBy: str
    projectId: str
    narrativeId: str
    inSituVisitRecordId: str
    record: InSituVisitRecordResponse | None
    narrative: StoredNarrativeResponse | None
    evidence: InSituVisitAuditEvidenceResponse
    cidoc: InSituVisitAuditCidocResponse
    facts: InSituVisitAuditFactsResponse
    generation: InSituVisitAuditGenerationResponse
    validation: InSituVisitAuditValidationResponse
    revisions: PaginatedNarrativeRevisionsResponse | None
