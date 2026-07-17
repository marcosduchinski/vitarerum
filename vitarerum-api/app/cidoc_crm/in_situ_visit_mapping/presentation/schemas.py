"""Pydantic request/response shapes for the In Situ Visit CIDOC mapping API,
matching 08InSituVisit-CIDOC-CRM.md exactly (camelCase JSON)."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

# ── Request ────────────────────────────────────────────────────────────────────


class AttachmentRequest(BaseModel):
    sourceId: str
    description: str = ""
    reference: str
    position: int


class RequestedObjectRequest(BaseModel):
    sourceId: str
    description: str = ""
    position: int


class OccurrenceRequest(BaseModel):
    sourceId: str
    description: str = ""
    position: int
    attachments: list[AttachmentRequest] = Field(default_factory=list)


class LogRequest(BaseModel):
    sourceId: str
    description: str = ""
    position: int
    attachments: list[AttachmentRequest] = Field(default_factory=list)


class PublicationRequest(BaseModel):
    sourceId: str
    description: str = ""
    position: int
    attachments: list[AttachmentRequest] = Field(default_factory=list)


class InSituVisitRecordRequest(BaseModel):
    code: str
    visitBeginDate: date
    visitEndDate: date
    visitorName: str
    placeName: str
    requestedObjects: list[RequestedObjectRequest] = Field(default_factory=list)
    inSituOccurrences: list[OccurrenceRequest] = Field(default_factory=list)
    inSituLogs: list[LogRequest] = Field(default_factory=list)
    inSituPublications: list[PublicationRequest] = Field(default_factory=list)


# ── Response ───────────────────────────────────────────────────────────────────


class AttachmentResponse(BaseModel):
    id: str
    sourceId: str
    description: str
    reference: str
    position: int
    mediaType: str | None = None


class RequestedObjectResponse(BaseModel):
    id: str
    sourceId: str
    description: str
    position: int
    displayTitle: str | None = None
    objectName: str | None = None
    briefDescriptionSnapshot: str | None = None


class OccurrenceResponse(BaseModel):
    id: str
    sourceId: str
    description: str
    position: int
    relatedObjectSourceId: str | None = None
    numberOfObjects: int | None = None
    occurrenceDate: datetime | None = None
    location: str | None = None
    reportedBy: str | None = None
    testimonial: str | None = None
    occurrenceLogDateConclusion: datetime | None = None
    occurrenceLogCurator: str | None = None
    attachments: list[AttachmentResponse]


class LogResponse(BaseModel):
    id: str
    sourceId: str
    description: str
    position: int
    relatedObjectSourceId: str | None = None
    numberOfObjects: int | None = None
    addedAt: datetime | None = None
    addedBy: str | None = None
    accessLogDateConclusion: datetime | None = None
    accessLogCurator: str | None = None
    attachments: list[AttachmentResponse]


class PublicationResponse(BaseModel):
    id: str
    sourceId: str
    description: str
    position: int
    relatedObjectSourceId: str | None = None
    addedAt: datetime | None = None
    addedBy: str | None = None
    attachments: list[AttachmentResponse]


class InSituVisitRecordResponse(BaseModel):
    id: str
    code: str
    visitBeginDate: date
    visitEndDate: date
    visitorName: str
    placeName: str
    generatedAt: datetime
    recordSchemaVersion: int | None = None
    sourceProjectId: str | None = None
    sourceProjectTitle: str | None = None
    sourceProjectPurpose: str | None = None
    plannedBeginDate: date | None = None
    plannedEndDate: date | None = None
    executionEvidenceType: str | None = None
    executionOccurredAt: datetime | None = None
    executionRecordedBy: str | None = None
    executionEvidenceGaps: list[str] = Field(default_factory=list)
    mappingVersion: str | None = None
    crmVersion: str | None = None
    approvedAt: datetime | None = None
    approvedBy: str | None = None
    approvalNote: str | None = None
    requestedObjects: list[RequestedObjectResponse]
    inSituOccurrences: list[OccurrenceResponse]
    inSituLogs: list[LogResponse]
    inSituPublications: list[PublicationResponse]


class PaginatedInSituVisitRecordsResponse(BaseModel):
    content: list[InSituVisitRecordResponse]
    page: int
    size: int
    totalElements: int
    totalPages: int
