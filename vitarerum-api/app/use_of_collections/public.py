"""Use of Collections' published language (Open Host Service).

This is the ONLY ``use_of_collections`` module downstream contexts (CIDOC-CRM
mapping) may import — enforced by import-linter. It exposes the read-only project
export view and the composition factory for the SQLAlchemy reader. Mirrors the
``app.identity.public`` pattern.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import TYPE_CHECKING

from app.use_of_collections.application.context_views import (
    ApprovalView,
    ExportAttachmentView,
    ExportEntryView,
    ExportObjectView,
    ProjectExportReader,
    ProjectExportView,
    VisitExecutionEvidenceView,
)
from app.use_of_collections.application.ports import ProjectFilters, ProposalFilters
from app.use_of_collections.domain.enums import ProposalStatus, UseStatus, UseType

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.identity.public import Actor
    from app.use_of_collections.domain.models import (
        CollectionUseObject,
        RequestedObject,
    )


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
    status: ProposalStatus
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
    status: UseStatus
    begin_date: date
    end_date: date
    objects: list[PublishedObjectView] = field(default_factory=list)
    requested_by_permission_id: str = ""
    origin_project_id: str | None = None
    proposal_id: str | None = None


@dataclass(slots=True)
class PublishableResourceView:
    id: str
    reference: str | None
    title: str | None
    status: str | None
    subtitle: str | None = None


def get_project_export_reader(session: AsyncSession) -> ProjectExportReader:
    """Default composition hook: the SQLAlchemy-backed ProjectExportReader."""
    from app.use_of_collections.infrastructure.repositories import (
        SqlAlchemyProjectExportReader,
    )

    return SqlAlchemyProjectExportReader(session)


def _proposal_object_view(obj: RequestedObject) -> PublishedObjectView:
    return PublishedObjectView(
        id=str(obj.id),
        inventory_number=obj.inventory_number,
        category=obj.category,
        description=obj.description,
        display_title=obj.display_title,
        object_name=obj.object_name,
        brief_description_snapshot=obj.brief_description_snapshot,
    )


def _project_object_view(obj: CollectionUseObject) -> PublishedObjectView:
    return PublishedObjectView(
        id=str(obj.id),
        inventory_number=obj.inventory_number,
        category=obj.category,
        description=obj.description,
        display_title=obj.display_title,
        object_name=obj.object_name,
        brief_description_snapshot=obj.brief_description_snapshot,
    )


class PublishedUseOfCollectionsReader:
    def __init__(self, session: AsyncSession) -> None:
        from app.use_of_collections.infrastructure.repositories import (
            SqlAlchemyCollectionUseProjectRepository,
            SqlAlchemyProposalRepository,
        )

        self._proposal_repo = SqlAlchemyProposalRepository(session)
        self._project_repo = SqlAlchemyCollectionUseProjectRepository(session)

    async def get_proposal(self, proposal_id: str) -> PublishedProposalView | None:
        from app.use_of_collections.domain.models import ProposalId

        proposal = await self._proposal_repo.get_by_id(ProposalId(proposal_id))
        if proposal is None or proposal.status != ProposalStatus.APPROVED:
            return None
        project = (
            await self._project_repo.get_by_id(proposal.collection_use_project_id)
            if proposal.collection_use_project_id is not None
            else None
        )
        return PublishedProposalView(
            id=str(proposal.id),
            reference_number=proposal.reference_number.value,
            title=proposal.title,
            purpose=project.purpose if project is not None else None,
            intended_use=proposal.intended_use,
            status=proposal.status,
            begin_date=proposal.begin_date,
            end_date=proposal.end_date,
            submitted_at=proposal.submitted_at,
            requested_objects=[
                _proposal_object_view(obj) for obj in proposal.requested_objects
            ],
            project_id=(
                str(proposal.collection_use_project_id)
                if proposal.collection_use_project_id is not None
                else None
            ),
        )

    async def get_project(self, project_id: str) -> PublishedProjectView | None:
        from app.use_of_collections.domain.models import CollectionUseProjectId

        project = await self._project_repo.get_by_id(CollectionUseProjectId(project_id))
        if project is None or project.status not in {
            UseStatus.IN_PROGRESS,
            UseStatus.COMPLETED,
        }:
            return None
        return PublishedProjectView(
            id=str(project.id),
            reference_number=project.reference_number.value,
            title=project.title,
            purpose=project.purpose,
            intended_use=project.intended_use,
            status=project.status,
            begin_date=project.begin_date,
            end_date=project.end_date,
            objects=[_project_object_view(obj) for obj in project.objects],
            requested_by_permission_id=str(project.requested_by),
            origin_project_id=(
                str(project.origin_project_id)
                if project.origin_project_id is not None
                else None
            ),
            proposal_id=str(project.proposal_id) if project.proposal_id else None,
        )

    async def list_publishable_proposals(
        self, q: str | None, page: int, size: int
    ) -> tuple[list[PublishableResourceView], int]:
        proposals, total = await self._proposal_repo.list(
            ProposalFilters(statuses=(ProposalStatus.APPROVED,), search=q),
            page,
            size,
        )
        return [
            PublishableResourceView(
                id=str(proposal.id),
                reference=proposal.reference_number.value,
                title=proposal.title,
                status=proposal.status.value,
                subtitle=(
                    proposal.intended_use.value
                    if proposal.intended_use is not None
                    else None
                ),
            )
            for proposal in proposals
        ], total

    async def list_publishable_projects(
        self, q: str | None, page: int, size: int
    ) -> tuple[list[PublishableResourceView], int]:
        # The existing repository accepts one status at a time. Query both MVP
        # statuses and merge a single requested page for the admin picker.
        in_progress, total_in_progress = await self._project_repo.list(
            ProjectFilters(status=UseStatus.IN_PROGRESS, search=q),
            0,
            max(size + page * size, 1),
        )
        completed, total_completed = await self._project_repo.list(
            ProjectFilters(status=UseStatus.COMPLETED, search=q),
            0,
            max(size + page * size, 1),
        )
        projects = sorted(
            [*in_progress, *completed],
            key=lambda project: project.begin_date,
            reverse=True,
        )
        start = page * size
        selected = projects[start : start + size]
        return [
            PublishableResourceView(
                id=str(project.id),
                reference=project.reference_number.value,
                title=project.title,
                status=project.status.value,
                subtitle=project.intended_use.value,
            )
            for project in selected
        ], total_in_progress + total_completed


def get_published_use_of_collections_reader(
    session: AsyncSession,
) -> PublishedUseOfCollectionsReader:
    return PublishedUseOfCollectionsReader(session)


class PublishedPublicationEntryWriter:
    """Narrow command facade used by downstream supervised workflows."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, *, project_id: str, caller: Actor, note: str) -> str:
        from app.reference_numbers.public import get_reference_generator
        from app.use_of_collections.application.use_cases.publication import (
            AddPublicationLogEntry,
            AddPublicationLogEntryInput,
        )
        from app.use_of_collections.domain.models import CollectionUseProjectId
        from app.use_of_collections.infrastructure.repositories import (
            SqlAlchemyCollectionUseProjectRepository,
            SqlAlchemyProposalRepository,
            SqlAlchemyPublicationLogRepository,
        )

        entry = await AddPublicationLogEntry(
            SqlAlchemyCollectionUseProjectRepository(self._session),
            SqlAlchemyPublicationLogRepository(self._session),
            SqlAlchemyProposalRepository(self._session),
            get_reference_generator(self._session),
        ).execute(
            AddPublicationLogEntryInput(
                project_id=CollectionUseProjectId(project_id),
                caller=caller,
                note=note,
            )
        )
        return str(entry.id)


def get_published_publication_entry_writer(
    session: AsyncSession,
) -> PublishedPublicationEntryWriter:
    return PublishedPublicationEntryWriter(session)


__all__ = [
    "ApprovalView",
    "ExportAttachmentView",
    "ExportEntryView",
    "ExportObjectView",
    "PublishedObjectView",
    "PublishedProjectView",
    "PublishedPublicationEntryWriter",
    "PublishedProposalView",
    "PublishedUseOfCollectionsReader",
    "PublishableResourceView",
    "ProjectExportReader",
    "ProjectExportView",
    "VisitExecutionEvidenceView",
    "get_published_use_of_collections_reader",
    "get_published_publication_entry_writer",
    "get_project_export_reader",
]
