from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.external_publications.application.ports import (
    Clock,
    ExternalPublicationAccessRepository,
    ExternalPublicationRepository,
    PublicationFilters,
    PublishableResourceFilters,
    PublishableResourceView,
    PublishedInSituVisitReportReader,
    PublishedProjectReader,
    PublishedProposalReader,
    TokenGenerator,
    TokenHasher,
)
from app.external_publications.domain.models import (
    ExternalPublication,
    ExternalPublicationAccess,
    ExternalPublicationAccessMode,
    ExternalPublicationAccessOutcome,
    ExternalPublicationId,
    ExternalPublicationProfile,
    ExternalPublicationResourceType,
    PublicationInaccessible,
)
from app.shared.kernel import PermissionId


class PublicationNotFound(LookupError):
    pass


class PublishedResourceNotFound(LookupError):
    pass


class PublishedResourceNotEligible(ValueError):
    pass


class JsonLdUnavailable(LookupError):
    pass


@dataclass(slots=True)
class CreateExternalPublicationInput:
    resource_type: ExternalPublicationResourceType
    resource_id: str
    access_mode: ExternalPublicationAccessMode
    profile: ExternalPublicationProfile
    created_by: PermissionId
    expires_at: datetime | None = None


@dataclass(slots=True)
class CreateExternalPublicationOutput:
    publication: ExternalPublication
    token: str | None


class CreateExternalPublication:
    def __init__(
        self,
        repository: ExternalPublicationRepository,
        proposal_reader: PublishedProposalReader,
        project_reader: PublishedProjectReader,
        report_reader: PublishedInSituVisitReportReader,
        token_generator: TokenGenerator,
        token_hasher: TokenHasher,
        clock: Clock,
    ) -> None:
        self._repo = repository
        self._proposal_reader = proposal_reader
        self._project_reader = project_reader
        self._report_reader = report_reader
        self._token_generator = token_generator
        self._token_hasher = token_hasher
        self._clock = clock

    async def execute(
        self, data: CreateExternalPublicationInput
    ) -> CreateExternalPublicationOutput:
        await self._ensure_publishable(data.resource_type, data.resource_id)
        raw_token = (
            self._token_generator.generate()
            if data.access_mode == ExternalPublicationAccessMode.TOKEN
            else None
        )
        publication = ExternalPublication.publish(
            resource_type=data.resource_type,
            resource_id=data.resource_id,
            access_mode=data.access_mode,
            profile=data.profile,
            created_by=data.created_by,
            token_hash=self._token_hasher.hash(raw_token) if raw_token else None,
            expires_at=data.expires_at,
            now=self._clock.now(),
        )
        await self._repo.add(publication)
        return CreateExternalPublicationOutput(publication=publication, token=raw_token)

    async def _ensure_publishable(
        self, resource_type: ExternalPublicationResourceType, resource_id: str
    ) -> None:
        if resource_type == ExternalPublicationResourceType.PROPOSAL:
            proposal = await self._proposal_reader.get(resource_id)
            if proposal is None:
                raise PublishedResourceNotFound("Published resource was not found")
            return
        if resource_type == ExternalPublicationResourceType.PROJECT:
            project = await self._project_reader.get(resource_id)
            if project is None:
                raise PublishedResourceNotFound("Published resource was not found")
            return
        report = await self._report_reader.get(resource_id)
        if report is None:
            raise PublishedResourceNotFound("Published resource was not found")
        if report.cidoc.conforms is not True:
            raise PublishedResourceNotEligible(
                "In-situ visit report is not CIDOC-conformant"
            )


class ListExternalPublications:
    def __init__(self, repository: ExternalPublicationRepository) -> None:
        self._repo = repository

    async def execute(
        self, filters: PublicationFilters, page: int, size: int
    ) -> tuple[list[ExternalPublication], int]:
        return await self._repo.list(filters, page, size)


class ListExternalPublicationAccesses:
    def __init__(
        self,
        publication_repository: ExternalPublicationRepository,
        access_repository: ExternalPublicationAccessRepository,
    ) -> None:
        self._publication_repo = publication_repository
        self._access_repo = access_repository

    async def execute(
        self, publication_id: ExternalPublicationId, page: int, size: int
    ) -> tuple[list[ExternalPublicationAccess], int]:
        publication = await self._publication_repo.get_by_id(publication_id)
        if publication is None:
            raise PublicationNotFound("External publication was not found")
        return await self._access_repo.list_by_publication(publication_id, page, size)


class ListPublishableResources:
    def __init__(
        self,
        proposal_reader: PublishedProposalReader,
        project_reader: PublishedProjectReader,
        report_reader: PublishedInSituVisitReportReader,
    ) -> None:
        self._proposal_reader = proposal_reader
        self._project_reader = project_reader
        self._report_reader = report_reader

    async def execute(
        self, filters: PublishableResourceFilters, page: int, size: int
    ) -> tuple[list[PublishableResourceView], int]:
        if filters.resource_type == ExternalPublicationResourceType.PROPOSAL:
            return await self._proposal_reader.list_publishable(filters.q, page, size)
        if filters.resource_type == ExternalPublicationResourceType.PROJECT:
            return await self._project_reader.list_publishable(filters.q, page, size)
        return await self._report_reader.list_publishable(filters.q, page, size)


class RevokeExternalPublication:
    def __init__(self, repository: ExternalPublicationRepository, clock: Clock) -> None:
        self._repo = repository
        self._clock = clock

    async def execute(
        self, publication_id: ExternalPublicationId, revoked_by: PermissionId
    ) -> ExternalPublication:
        publication = await self._repo.get_by_id(publication_id)
        if publication is None:
            raise PublicationNotFound("External publication was not found")
        publication.revoke(revoked_by=revoked_by, now=self._clock.now())
        await self._repo.save(publication)
        return publication


@dataclass(slots=True)
class ResolveExternalPublicationOutput:
    publication: ExternalPublication
    resource: Any


class ResolveExternalPublication:
    def __init__(
        self,
        repository: ExternalPublicationRepository,
        access_repository: ExternalPublicationAccessRepository,
        proposal_reader: PublishedProposalReader,
        project_reader: PublishedProjectReader,
        report_reader: PublishedInSituVisitReportReader,
        token_hasher: TokenHasher,
        clock: Clock,
    ) -> None:
        self._repo = repository
        self._access_repo = access_repository
        self._proposal_reader = proposal_reader
        self._project_reader = project_reader
        self._report_reader = report_reader
        self._token_hasher = token_hasher
        self._clock = clock

    async def execute(
        self,
        raw_token: str,
        *,
        remote_addr_hash: str | None = None,
        user_agent: str | None = None,
    ) -> ResolveExternalPublicationOutput:
        token_hash = self._token_hasher.hash(raw_token)
        publication = await self._repo.get_by_token_hash(token_hash)
        if publication is None:
            await self._access_repo.add(
                ExternalPublicationAccess.record(
                    publication_id=None,
                    access_mode=ExternalPublicationAccessMode.TOKEN,
                    outcome=ExternalPublicationAccessOutcome.DENIED,
                    remote_addr_hash=remote_addr_hash,
                    user_agent=user_agent,
                    now=self._clock.now(),
                )
            )
            raise PublicationNotFound("External publication was not found")
        try:
            publication.ensure_accessible(self._clock.now())
            resource = await self._load_resource(publication)
            if resource is None:
                raise PublishedResourceNotFound("Published resource was not found")
        except (PublicationInaccessible, PublishedResourceNotFound):
            await self._record_access(
                publication,
                ExternalPublicationAccessOutcome.DENIED,
                remote_addr_hash,
                user_agent,
            )
            raise PublicationNotFound("External publication was not found") from None
        await self._record_access(
            publication,
            ExternalPublicationAccessOutcome.GRANTED,
            remote_addr_hash,
            user_agent,
        )
        return ResolveExternalPublicationOutput(
            publication=publication,
            resource=resource,
        )

    async def _load_resource(self, publication: ExternalPublication) -> Any:
        if publication.resource_type == ExternalPublicationResourceType.PROPOSAL:
            return await self._proposal_reader.get(publication.resource_id)
        if publication.resource_type == ExternalPublicationResourceType.PROJECT:
            return await self._project_reader.get(publication.resource_id)
        return await self._report_reader.get(publication.resource_id)

    async def _record_access(
        self,
        publication: ExternalPublication,
        outcome: ExternalPublicationAccessOutcome,
        remote_addr_hash: str | None,
        user_agent: str | None,
    ) -> None:
        await self._access_repo.add(
            ExternalPublicationAccess.record(
                publication_id=publication.id,
                access_mode=publication.access_mode,
                outcome=outcome,
                integration_client_id=publication.integration_client_id,
                remote_addr_hash=remote_addr_hash,
                user_agent=user_agent,
                now=self._clock.now(),
            )
        )


class GetExternalPublishedJsonLd:
    def __init__(
        self,
        resolver: ResolveExternalPublication,
        report_reader: PublishedInSituVisitReportReader,
    ) -> None:
        self._resolver = resolver
        self._report_reader = report_reader

    async def execute(
        self,
        raw_token: str,
        *,
        remote_addr_hash: str | None = None,
        user_agent: str | None = None,
    ) -> dict[str, Any]:
        resolved = await self._resolver.execute(
            raw_token,
            remote_addr_hash=remote_addr_hash,
            user_agent=user_agent,
        )
        publication = resolved.publication
        if (
            publication.resource_type
            != ExternalPublicationResourceType.IN_SITU_VISIT_REPORT
        ):
            raise JsonLdUnavailable("JSON-LD is available only for in-situ reports")
        if publication.profile not in {
            ExternalPublicationProfile.DETAIL,
            ExternalPublicationProfile.JSON_LD,
        }:
            raise JsonLdUnavailable("Publication profile does not allow JSON-LD")
        document = await self._report_reader.get_json_ld(publication.resource_id)
        if document is None:
            raise JsonLdUnavailable("JSON-LD document is unavailable")
        return document
