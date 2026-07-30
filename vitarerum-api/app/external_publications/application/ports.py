from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Protocol

from app.external_publications.domain.models import (
    ExternalProjectStatus,
    ExternalProposalStatus,
    ExternalPublication,
    ExternalPublicationAccess,
    ExternalPublicationId,
    ExternalPublicationProfile,
    ExternalPublicationResourceType,
    ExternalPublicationStatus,
)
from app.shared.kernel import UseType


@dataclass(slots=True)
class PublishedObjectView:
    id: str
    inventory_number: str
    category: str
    description: str
    display_title: str | None = None
    object_name: str | None = None
    brief_description_snapshot: str | None = None


@dataclass(slots=True)
class PublishedProposalView:
    id: str
    reference_number: str
    title: str | None
    purpose: str | None
    intended_use: UseType | None
    status: ExternalProposalStatus
    begin_date: date | None
    end_date: date | None
    submitted_at: datetime
    requested_objects: list[PublishedObjectView] = field(default_factory=list)
    project_id: str | None = None


@dataclass(slots=True)
class PublishedProjectView:
    id: str
    reference_number: str
    title: str
    purpose: str
    intended_use: UseType
    status: ExternalProjectStatus
    begin_date: date
    end_date: date
    objects: list[PublishedObjectView] = field(default_factory=list)
    origin_project_id: str | None = None
    proposal_id: str | None = None


@dataclass(slots=True)
class PublishedNarrativeView:
    id: str
    text: str


@dataclass(slots=True)
class PublishedInSituVisitCidocView:
    record_id: str
    json_ld: dict[str, Any] | None
    conforms: bool | None
    mapping_version: str | None
    crm_version: str | None


@dataclass(slots=True)
class PublishedInSituVisitReportView:
    id: str
    project_id: str
    created_at: datetime
    code: str | None
    visitor_name: str | None
    place_name: str | None
    visit_begin_date: date | None
    visit_end_date: date | None
    narrative: PublishedNarrativeView | None
    cidoc: PublishedInSituVisitCidocView


@dataclass(slots=True)
class PublishableResourceView:
    id: str
    resource_type: ExternalPublicationResourceType
    reference: str | None
    title: str | None
    status: str | None
    subtitle: str | None = None


@dataclass(slots=True)
class PublicationFilters:
    resource_type: ExternalPublicationResourceType | None = None
    resource_id: str | None = None
    status: ExternalPublicationStatus | None = None
    profile: ExternalPublicationProfile | None = None
    q: str | None = None


@dataclass(slots=True)
class PublishableResourceFilters:
    resource_type: ExternalPublicationResourceType
    q: str | None = None


class ExternalPublicationRepository(Protocol):
    async def add(self, publication: ExternalPublication) -> None: ...

    async def get_by_id(
        self, publication_id: ExternalPublicationId
    ) -> ExternalPublication | None: ...

    async def get_by_token_hash(
        self, token_hash: str
    ) -> ExternalPublication | None: ...

    async def save(self, publication: ExternalPublication) -> None: ...

    async def list(
        self, filters: PublicationFilters, page: int, size: int
    ) -> tuple[list[ExternalPublication], int]: ...


class ExternalPublicationAccessRepository(Protocol):
    async def add(self, access: ExternalPublicationAccess) -> None: ...

    async def list_by_publication(
        self, publication_id: ExternalPublicationId, page: int, size: int
    ) -> tuple[list[ExternalPublicationAccess], int]: ...


class PublishedProposalReader(Protocol):
    async def get(self, proposal_id: str) -> PublishedProposalView | None: ...

    async def list_publishable(
        self, q: str | None, page: int, size: int
    ) -> tuple[list[PublishableResourceView], int]: ...


class PublishedProjectReader(Protocol):
    async def get(self, project_id: str) -> PublishedProjectView | None: ...

    async def list_publishable(
        self, q: str | None, page: int, size: int
    ) -> tuple[list[PublishableResourceView], int]: ...


class PublishedInSituVisitReportReader(Protocol):
    async def get(self, report_id: str) -> PublishedInSituVisitReportView | None: ...

    async def get_json_ld(self, report_id: str) -> dict[str, Any] | None: ...

    async def list_publishable(
        self, q: str | None, page: int, size: int
    ) -> tuple[list[PublishableResourceView], int]: ...


class Clock(Protocol):
    def now(self) -> datetime: ...


class TokenGenerator(Protocol):
    def generate(self) -> str: ...


class TokenHasher(Protocol):
    def hash(self, raw_token: str) -> str: ...
