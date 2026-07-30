from __future__ import annotations

from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.external_publications.application.ports import (
    PublishableResourceView,
    PublishedInSituVisitCidocView,
    PublishedInSituVisitReportView,
    PublishedNarrativeView,
    PublishedObjectView,
    PublishedProjectView,
    PublishedProposalView,
)
from app.external_publications.domain.models import (
    ExternalProjectStatus,
    ExternalProposalStatus,
    ExternalPublicationResourceType,
)


class _ObjectLike(Protocol):
    id: str
    inventory_number: str
    category: str
    description: str
    display_title: str | None
    object_name: str | None
    brief_description_snapshot: str | None


class _PublishableLike(Protocol):
    id: str
    reference: str | None
    title: str | None
    status: str | None
    subtitle: str | None


class UseOfCollectionsPublicationAcl:
    def __init__(self, session: AsyncSession) -> None:
        from app.use_of_collections.public import (
            get_published_use_of_collections_reader,
        )

        self._reader = get_published_use_of_collections_reader(session)

    async def get_proposal(self, proposal_id: str) -> PublishedProposalView | None:
        proposal = await self._reader.get_proposal(proposal_id)
        if proposal is None:
            return None
        return PublishedProposalView(
            id=proposal.id,
            reference_number=proposal.reference_number,
            title=proposal.title,
            purpose=proposal.purpose,
            intended_use=proposal.intended_use,
            status=ExternalProposalStatus(proposal.status.value),
            begin_date=proposal.begin_date,
            end_date=proposal.end_date,
            submitted_at=proposal.submitted_at,
            requested_objects=[_object_view(obj) for obj in proposal.requested_objects],
            project_id=proposal.project_id,
        )

    async def get_project(self, project_id: str) -> PublishedProjectView | None:
        project = await self._reader.get_project(project_id)
        if project is None:
            return None
        return PublishedProjectView(
            id=project.id,
            reference_number=project.reference_number,
            title=project.title,
            purpose=project.purpose,
            intended_use=project.intended_use,
            status=ExternalProjectStatus(project.status.value),
            begin_date=project.begin_date,
            end_date=project.end_date,
            objects=[_object_view(obj) for obj in project.objects],
            origin_project_id=project.origin_project_id,
            proposal_id=project.proposal_id,
        )

    async def list_publishable_proposals(
        self, q: str | None, page: int, size: int
    ) -> tuple[list[PublishableResourceView], int]:
        items, total = await self._reader.list_publishable_proposals(q, page, size)
        return [
            _publishable_view(item, ExternalPublicationResourceType.PROPOSAL)
            for item in items
        ], total

    async def list_publishable_projects(
        self, q: str | None, page: int, size: int
    ) -> tuple[list[PublishableResourceView], int]:
        items, total = await self._reader.list_publishable_projects(q, page, size)
        return [
            _publishable_view(item, ExternalPublicationResourceType.PROJECT)
            for item in items
        ], total


class ProposalPublicationReader:
    def __init__(self, acl: UseOfCollectionsPublicationAcl) -> None:
        self._acl = acl

    async def get(self, proposal_id: str) -> PublishedProposalView | None:
        return await self._acl.get_proposal(proposal_id)

    async def list_publishable(
        self, q: str | None, page: int, size: int
    ) -> tuple[list[PublishableResourceView], int]:
        return await self._acl.list_publishable_proposals(q, page, size)


class ProjectPublicationReader:
    def __init__(self, acl: UseOfCollectionsPublicationAcl) -> None:
        self._acl = acl

    async def get(self, project_id: str) -> PublishedProjectView | None:
        return await self._acl.get_project(project_id)

    async def list_publishable(
        self, q: str | None, page: int, size: int
    ) -> tuple[list[PublishableResourceView], int]:
        return await self._acl.list_publishable_projects(q, page, size)


class ReportsPublicationAcl:
    def __init__(self, session: AsyncSession) -> None:
        from app.reports.public import get_published_in_situ_visit_report_reader

        self._reader = get_published_in_situ_visit_report_reader(session)

    async def get(self, report_id: str) -> PublishedInSituVisitReportView | None:
        report = await self._reader.get(report_id)
        if report is None:
            return None
        return PublishedInSituVisitReportView(
            id=report.id,
            project_id=report.project_id,
            created_at=report.created_at,
            code=report.code,
            visitor_name=report.visitor_name,
            place_name=report.place_name,
            visit_begin_date=report.visit_begin_date,
            visit_end_date=report.visit_end_date,
            narrative=(
                PublishedNarrativeView(
                    id=report.narrative.id,
                    text=report.narrative.text,
                )
                if report.narrative is not None
                else None
            ),
            cidoc=PublishedInSituVisitCidocView(
                record_id=report.cidoc.record_id,
                json_ld=report.cidoc.json_ld,
                conforms=report.cidoc.conforms,
                mapping_version=report.cidoc.mapping_version,
                crm_version=report.cidoc.crm_version,
            ),
        )

    async def get_json_ld(self, report_id: str) -> dict[str, Any] | None:
        return await self._reader.get_json_ld(report_id)

    async def list_publishable(
        self, q: str | None, page: int, size: int
    ) -> tuple[list[PublishableResourceView], int]:
        items, total = await self._reader.list_publishable(q, page, size)
        return [
            _publishable_view(
                item,
                ExternalPublicationResourceType.IN_SITU_VISIT_REPORT,
            )
            for item in items
        ], total


def _object_view(obj: _ObjectLike) -> PublishedObjectView:
    return PublishedObjectView(
        id=obj.id,
        inventory_number=obj.inventory_number,
        category=obj.category,
        description=obj.description,
        display_title=obj.display_title,
        object_name=obj.object_name,
        brief_description_snapshot=obj.brief_description_snapshot,
    )


def _publishable_view(
    item: _PublishableLike,
    resource_type: ExternalPublicationResourceType,
) -> PublishableResourceView:
    return PublishableResourceView(
        id=item.id,
        resource_type=resource_type,
        reference=item.reference,
        title=item.title,
        status=item.status,
        subtitle=item.subtitle,
    )
