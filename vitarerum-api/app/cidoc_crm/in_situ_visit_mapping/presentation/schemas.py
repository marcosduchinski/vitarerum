"""Pydantic request/response shapes for the In Situ Visit CEDOC mapping API,
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


class RequestedObjectResponse(BaseModel):
    id: str
    sourceId: str
    description: str
    position: int


class OccurrenceResponse(BaseModel):
    id: str
    sourceId: str
    description: str
    position: int
    attachments: list[AttachmentResponse]


class LogResponse(BaseModel):
    id: str
    sourceId: str
    description: str
    position: int
    attachments: list[AttachmentResponse]


class PublicationResponse(BaseModel):
    id: str
    sourceId: str
    description: str
    position: int
    attachments: list[AttachmentResponse]


class InSituVisitRecordResponse(BaseModel):
    id: str
    code: str
    visitBeginDate: date
    visitEndDate: date
    visitorName: str
    placeName: str
    generatedAt: datetime
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
