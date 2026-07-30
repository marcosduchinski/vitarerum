from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from app.external_publications.application.ports import (
    PublicationFilters,
    PublishableResourceFilters,
    PublishableResourceView,
    PublishedInSituVisitCidocView,
    PublishedInSituVisitReportView,
    PublishedNarrativeView,
    PublishedObjectView,
    PublishedProjectView,
    PublishedProposalView,
)
from app.external_publications.application.use_cases import (
    CreateExternalPublication,
    CreateExternalPublicationInput,
    GetExternalPublishedJsonLd,
    JsonLdUnavailable,
    ListPublishableResources,
    PublishedResourceNotEligible,
    ResolveExternalPublication,
)
from app.external_publications.domain.models import (
    ExternalProjectStatus,
    ExternalProposalStatus,
    ExternalPublication,
    ExternalPublicationAccess,
    ExternalPublicationAccessMode,
    ExternalPublicationAccessOutcome,
    ExternalPublicationId,
    ExternalPublicationProfile,
    ExternalPublicationResourceType,
    ExternalPublicationStatus,
    PublicationInaccessible,
)
from app.shared.kernel import PermissionId, UseType
from app.shared.tokens import hash_opaque_token

_NOW = datetime(2026, 7, 29, 12, 0, tzinfo=UTC)


class _Clock:
    def now(self) -> datetime:
        return _NOW


class _TokenGenerator:
    def generate(self) -> str:
        return "raw-token"


class _TokenHasher:
    def hash(self, raw_token: str) -> str:
        return hash_opaque_token(raw_token)


class _PublicationRepo:
    def __init__(self) -> None:
        self.items: dict[str, ExternalPublication] = {}

    async def add(self, publication: ExternalPublication) -> None:
        self.items[publication.id] = publication

    async def get_by_id(
        self, publication_id: ExternalPublicationId
    ) -> ExternalPublication | None:
        return self.items.get(publication_id)

    async def get_by_token_hash(self, token_hash: str) -> ExternalPublication | None:
        return next(
            (item for item in self.items.values() if item.token_hash == token_hash),
            None,
        )

    async def save(self, publication: ExternalPublication) -> None:
        self.items[publication.id] = publication

    async def list(
        self, filters: PublicationFilters, page: int, size: int
    ) -> tuple[list[ExternalPublication], int]:
        items = list(self.items.values())
        return items[page * size : page * size + size], len(items)


class _AccessRepo:
    def __init__(self) -> None:
        self.items: list[ExternalPublicationAccess] = []

    async def add(self, access: ExternalPublicationAccess) -> None:
        self.items.append(access)

    async def list_by_publication(
        self, publication_id: ExternalPublicationId, page: int, size: int
    ) -> tuple[list[ExternalPublicationAccess], int]:
        items = [item for item in self.items if item.publication_id == publication_id]
        return items[page * size : page * size + size], len(items)


class _ProposalReader:
    async def get(self, proposal_id: str) -> PublishedProposalView | None:
        if proposal_id != "proposal-1":
            return None
        return PublishedProposalView(
            id=proposal_id,
            reference_number="CUP-1",
            title="Proposal",
            purpose="Research",
            intended_use=UseType.IN_SITU_VISIT,
            status=ExternalProposalStatus.APPROVED,
            begin_date=None,
            end_date=None,
            submitted_at=_NOW,
            requested_objects=[
                PublishedObjectView(
                    id="obj-1",
                    inventory_number="INV",
                    category="Specimen",
                    description="Object",
                )
            ],
            project_id="project-1",
        )

    async def list_publishable(
        self, q: str | None, page: int, size: int
    ) -> tuple[list[PublishableResourceView], int]:
        return [
            PublishableResourceView(
                id="proposal-1",
                resource_type=ExternalPublicationResourceType.PROPOSAL,
                reference="CUP-1",
                title="Proposal",
                status="APPROVED",
            )
        ], 1


class _ProjectReader:
    async def get(self, project_id: str) -> PublishedProjectView | None:
        if project_id != "project-1":
            return None
        return PublishedProjectView(
            id=project_id,
            reference_number="CUP-1",
            title="Project",
            purpose="Research",
            intended_use=UseType.IN_SITU_VISIT,
            status=ExternalProjectStatus.COMPLETED,
            begin_date=_NOW.date(),
            end_date=_NOW.date(),
            proposal_id="proposal-1",
        )

    async def list_publishable(
        self, q: str | None, page: int, size: int
    ) -> tuple[list[PublishableResourceView], int]:
        return [], 0


@dataclass(slots=True)
class _ReportReader:
    conforms: bool | None = True

    async def get(self, report_id: str) -> PublishedInSituVisitReportView | None:
        if report_id != "report-1":
            return None
        return PublishedInSituVisitReportView(
            id=report_id,
            project_id="project-1",
            created_at=_NOW,
            code="VISIT-1",
            visitor_name="Visitor",
            place_name="Room",
            visit_begin_date=_NOW.date(),
            visit_end_date=_NOW.date(),
            narrative=PublishedNarrativeView(id="narrative-1", text="Narrative"),
            cidoc=PublishedInSituVisitCidocView(
                record_id="record-1",
                json_ld={"@context": {}, "@graph": []},
                conforms=self.conforms,
                mapping_version="mapping-v1",
                crm_version="7.1.3",
            ),
        )

    async def get_json_ld(self, report_id: str) -> dict[str, object] | None:
        if report_id == "report-1":
            return {"@context": {}, "@graph": []}
        return None

    async def list_publishable(
        self, q: str | None, page: int, size: int
    ) -> tuple[list[PublishableResourceView], int]:
        return [], 0


def _create_use_case(
    repo: _PublicationRepo,
    report_reader: _ReportReader | None = None,
) -> CreateExternalPublication:
    return CreateExternalPublication(
        repo,
        _ProposalReader(),
        _ProjectReader(),
        report_reader or _ReportReader(),
        _TokenGenerator(),
        _TokenHasher(),
        _Clock(),
    )


async def test_create_external_publication_hashes_token_once() -> None:
    repo = _PublicationRepo()

    output = await _create_use_case(repo).execute(
        CreateExternalPublicationInput(
            resource_type=ExternalPublicationResourceType.PROPOSAL,
            resource_id="proposal-1",
            access_mode=ExternalPublicationAccessMode.TOKEN,
            profile=ExternalPublicationProfile.DETAIL,
            created_by=PermissionId("perm-admin"),
        )
    )

    assert output.token == "raw-token"
    assert output.publication.token_hash == hash_opaque_token("raw-token")
    assert output.publication.token_hash != output.token
    assert list(repo.items.values()) == [output.publication]


async def test_rejects_non_conformant_report_publication() -> None:
    repo = _PublicationRepo()

    with pytest.raises(PublishedResourceNotEligible):
        await _create_use_case(repo, _ReportReader(conforms=False)).execute(
            CreateExternalPublicationInput(
                resource_type=ExternalPublicationResourceType.IN_SITU_VISIT_REPORT,
                resource_id="report-1",
                access_mode=ExternalPublicationAccessMode.TOKEN,
                profile=ExternalPublicationProfile.DETAIL,
                created_by=PermissionId("perm-admin"),
            )
        )


async def test_resolve_returns_404_semantics_for_revoked_publication() -> None:
    repo = _PublicationRepo()
    access_repo = _AccessRepo()
    output = await _create_use_case(repo).execute(
        CreateExternalPublicationInput(
            resource_type=ExternalPublicationResourceType.PROPOSAL,
            resource_id="proposal-1",
            access_mode=ExternalPublicationAccessMode.TOKEN,
            profile=ExternalPublicationProfile.DETAIL,
            created_by=PermissionId("perm-admin"),
        )
    )
    output.publication.revoke(revoked_by=PermissionId("perm-admin"), now=_NOW)

    resolver = ResolveExternalPublication(
        repo,
        access_repo,
        _ProposalReader(),
        _ProjectReader(),
        _ReportReader(),
        _TokenHasher(),
        _Clock(),
    )

    with pytest.raises(LookupError):
        await resolver.execute("raw-token")

    assert len(access_repo.items) == 1
    assert access_repo.items[0].publication_id == output.publication.id


async def test_resolve_records_granted_access() -> None:
    repo = _PublicationRepo()
    access_repo = _AccessRepo()
    output = await _create_use_case(repo).execute(
        CreateExternalPublicationInput(
            resource_type=ExternalPublicationResourceType.PROPOSAL,
            resource_id="proposal-1",
            access_mode=ExternalPublicationAccessMode.TOKEN,
            profile=ExternalPublicationProfile.DETAIL,
            created_by=PermissionId("perm-admin"),
        )
    )
    resolver = ResolveExternalPublication(
        repo,
        access_repo,
        _ProposalReader(),
        _ProjectReader(),
        _ReportReader(),
        _TokenHasher(),
        _Clock(),
    )

    resolved = await resolver.execute("raw-token", user_agent="test-agent")

    assert resolved.publication == output.publication
    assert len(access_repo.items) == 1
    assert access_repo.items[0].publication_id == output.publication.id
    assert access_repo.items[0].outcome == ExternalPublicationAccessOutcome.GRANTED
    assert access_repo.items[0].user_agent == "test-agent"


async def test_json_ld_is_returned_for_report_detail_publication() -> None:
    repo = _PublicationRepo()
    access_repo = _AccessRepo()
    output = await _create_use_case(repo).execute(
        CreateExternalPublicationInput(
            resource_type=ExternalPublicationResourceType.IN_SITU_VISIT_REPORT,
            resource_id="report-1",
            access_mode=ExternalPublicationAccessMode.TOKEN,
            profile=ExternalPublicationProfile.DETAIL,
            created_by=PermissionId("perm-admin"),
        )
    )
    assert output.publication.status == ExternalPublicationStatus.PUBLISHED
    resolver = ResolveExternalPublication(
        repo,
        access_repo,
        _ProposalReader(),
        _ProjectReader(),
        _ReportReader(),
        _TokenHasher(),
        _Clock(),
    )
    use_case = GetExternalPublishedJsonLd(resolver, _ReportReader())

    assert await use_case.execute("raw-token") == {"@context": {}, "@graph": []}


async def test_json_ld_rejects_summary_profile() -> None:
    repo = _PublicationRepo()
    access_repo = _AccessRepo()
    output = await _create_use_case(repo).execute(
        CreateExternalPublicationInput(
            resource_type=ExternalPublicationResourceType.IN_SITU_VISIT_REPORT,
            resource_id="report-1",
            access_mode=ExternalPublicationAccessMode.TOKEN,
            profile=ExternalPublicationProfile.SUMMARY,
            created_by=PermissionId("perm-admin"),
        )
    )
    assert output.publication.profile == ExternalPublicationProfile.SUMMARY
    resolver = ResolveExternalPublication(
        repo,
        access_repo,
        _ProposalReader(),
        _ProjectReader(),
        _ReportReader(),
        _TokenHasher(),
        _Clock(),
    )
    use_case = GetExternalPublishedJsonLd(resolver, _ReportReader())

    with pytest.raises(JsonLdUnavailable):
        await use_case.execute("raw-token")


def test_domain_blocks_expired_publication() -> None:
    publication = ExternalPublication.publish(
        resource_type=ExternalPublicationResourceType.PROPOSAL,
        resource_id="proposal-1",
        access_mode=ExternalPublicationAccessMode.TOKEN,
        profile=ExternalPublicationProfile.DETAIL,
        created_by=PermissionId("perm-admin"),
        token_hash=hash_opaque_token("raw-token"),
        expires_at=_NOW - timedelta(seconds=1),
        now=_NOW - timedelta(hours=1),
    )

    with pytest.raises(PublicationInaccessible):
        publication.ensure_accessible(_NOW)


def test_domain_normalizes_naive_expiration_before_access_check() -> None:
    publication = ExternalPublication.publish(
        resource_type=ExternalPublicationResourceType.PROPOSAL,
        resource_id="proposal-1",
        access_mode=ExternalPublicationAccessMode.TOKEN,
        profile=ExternalPublicationProfile.DETAIL,
        created_by=PermissionId("perm-admin"),
        token_hash=hash_opaque_token("raw-token"),
        expires_at=datetime(2026, 7, 29, 12, 1),
        now=_NOW,
    )

    publication.ensure_accessible(_NOW)

    with pytest.raises(PublicationInaccessible):
        publication.ensure_accessible(datetime(2026, 7, 29, 12, 1, tzinfo=UTC))


async def test_list_publishable_resources_delegates_by_type() -> None:
    items, total = await ListPublishableResources(
        _ProposalReader(),
        _ProjectReader(),
        _ReportReader(),
    ).execute(
        filters=PublishableResourceFilters(
            resource_type=ExternalPublicationResourceType.PROPOSAL,
            q=None,
        ),
        page=0,
        size=20,
    )

    assert total == 1
    assert items[0].id == "proposal-1"
