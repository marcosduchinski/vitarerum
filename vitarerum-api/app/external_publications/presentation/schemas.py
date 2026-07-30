from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

from app.external_publications.domain.models import (
    ExternalProjectStatus,
    ExternalProposalStatus,
    ExternalPublicationAccessMode,
    ExternalPublicationProfile,
    ExternalPublicationResourceType,
    ExternalPublicationStatus,
)
from app.shared.kernel import UseType


class CreateExternalPublicationRequest(BaseModel):
    resourceType: ExternalPublicationResourceType
    resourceId: str
    accessMode: ExternalPublicationAccessMode = ExternalPublicationAccessMode.TOKEN
    profile: ExternalPublicationProfile = ExternalPublicationProfile.DETAIL
    expiresAt: datetime | None = None


class ExternalPublicationResponse(BaseModel):
    id: str
    resourceType: ExternalPublicationResourceType
    resourceId: str
    status: ExternalPublicationStatus
    accessMode: ExternalPublicationAccessMode
    profile: ExternalPublicationProfile
    expiresAt: datetime | None = None
    url: str | None = None
    createdAt: datetime
    publishedAt: datetime
    revokedAt: datetime | None = None


class PaginatedExternalPublicationsResponse(BaseModel):
    content: list[ExternalPublicationResponse]
    page: int
    size: int
    totalElements: int
    totalPages: int


class PublishableResourceResponse(BaseModel):
    id: str
    resourceType: ExternalPublicationResourceType
    reference: str | None = None
    title: str | None = None
    status: str | None = None
    subtitle: str | None = None


class PaginatedPublishableResourcesResponse(BaseModel):
    content: list[PublishableResourceResponse]
    page: int
    size: int
    totalElements: int
    totalPages: int


class ExternalObjectResponse(BaseModel):
    id: str
    inventoryNumber: str
    displayTitle: str | None = None
    objectName: str | None = None
    briefDescriptionSnapshot: str | None = None
    category: str
    description: str


class ExternalProposalResponse(BaseModel):
    type: str = "proposal"
    id: str
    referenceNumber: str
    title: str | None = None
    purpose: str | None = None
    intendedUse: UseType | None = None
    status: ExternalProposalStatus
    beginDate: date | None = None
    endDate: date | None = None
    submittedAt: datetime
    requestedObjects: list[ExternalObjectResponse] = Field(default_factory=list)
    projectId: str | None = None


class ExternalProjectResponse(BaseModel):
    type: str = "project"
    id: str
    referenceNumber: str
    title: str
    purpose: str | None = None
    intendedUse: UseType | None = None
    status: ExternalProjectStatus
    beginDate: date | None = None
    endDate: date | None = None
    objects: list[ExternalObjectResponse] = Field(default_factory=list)
    originProjectId: str | None = None
    proposalId: str | None = None


class ExternalNarrativeResponse(BaseModel):
    id: str
    text: str


class ExternalCidocResponse(BaseModel):
    recordId: str
    jsonLdUrl: str
    conforms: bool | None = None
    mappingVersion: str | None = None
    crmVersion: str | None = None


class ExternalInSituVisitReportResponse(BaseModel):
    type: str = "in_situ_visit_report"
    id: str
    projectId: str
    createdAt: datetime
    code: str | None = None
    visitorName: str | None = None
    placeName: str | None = None
    visitBeginDate: date | None = None
    visitEndDate: date | None = None
    narrative: ExternalNarrativeResponse | None = None
    cidoc: ExternalCidocResponse


ExternalPublishedResourceResponse = (
    ExternalProposalResponse
    | ExternalProjectResponse
    | ExternalInSituVisitReportResponse
)


JsonLdDocument = dict[str, Any]


class ExternalPublicationAccessResponse(BaseModel):
    id: str
    publicationId: str | None = None
    accessedAt: datetime
    accessMode: ExternalPublicationAccessMode
    integrationClientId: str | None = None
    remoteAddrHash: str | None = None
    userAgent: str | None = None
    outcome: str


class PaginatedExternalPublicationAccessesResponse(BaseModel):
    content: list[ExternalPublicationAccessResponse]
    page: int
    size: int
    totalElements: int
    totalPages: int
