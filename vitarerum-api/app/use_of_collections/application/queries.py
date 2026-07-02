"""Read-side query services (lightweight CQRS, HEXAGONAL_UP.md Step 6).

Query services own the read orchestration the routes used to do: repository
access, cross-aggregate joins (project ↔ proposal), caller scoping rules, and
permission-view resolution through Identity's published PermissionReader
(deduplicated per request). They return application read models — domain
objects plus PermissionViews — never Pydantic schemas; presentation maps them
onto the existing response classes, so the JSON contract is untouched.

Scope (recorded decision): the four heaviest endpoint groups — proposals
list/detail and projects list/detail. The remaining reads (events,
conversation, documents, journal listings) are thin repo-call-and-map handlers
and stay in presentation.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.identity.public import Actor, PermissionReader, PermissionView
from app.shared.authorization import is_staff
from app.use_of_collections.application.authorization import (
    assert_project_access,
    assert_proposal_access,
)
from app.use_of_collections.application.ports import (
    CollectionUseProjectRepository,
    ConversationRepository,
    ProjectFilters,
    ProposalFilters,
    ProposalRepository,
)
from app.use_of_collections.domain.models import (
    CollectionUseProject,
    CollectionUseProjectId,
    PermissionId,
    Proposal,
    ProposalId,
)


async def _resolve_views(
    reader: PermissionReader,
    permission_ids: list[PermissionId | None],
) -> dict[str, PermissionView]:
    """Resolve each distinct permission id once; unresolved ids are absent."""
    views: dict[str, PermissionView] = {}
    for permission_id in permission_ids:
        if permission_id is None or permission_id in views:
            continue
        view = await reader.get_detail(permission_id)
        if view is not None:
            views[permission_id] = view
    return views


# ── Proposals ─────────────────────────────────────────────────────────────────


@dataclass(slots=True)
class ProposalListItemView:
    proposal: Proposal
    requested_by: PermissionView | None
    assigned_to: PermissionView | None


@dataclass(slots=True)
class ProposalListPage:
    items: list[ProposalListItemView]
    total: int


class ListProposals:
    def __init__(
        self,
        proposal_repository: ProposalRepository,
        permission_reader: PermissionReader,
    ) -> None:
        self._repo = proposal_repository
        self._reader = permission_reader

    async def execute(
        self,
        caller: Actor,
        filters: ProposalFilters,
        page: int,
        size: int,
    ) -> ProposalListPage:
        # Non-staff are always scoped to their own proposals; the filter value
        # is honoured only for staff so a requester cannot read others'.
        if not is_staff(caller):
            filters.requested_by = caller.id
        proposals, total = await self._repo.list(filters, page, size)
        permission_ids: list[PermissionId | None] = [
            *(p.requested_by for p in proposals),
            *(p.assigned_to for p in proposals),
        ]
        views = await _resolve_views(self._reader, permission_ids)
        items = [
            ProposalListItemView(
                proposal=p,
                requested_by=views.get(p.requested_by) if p.requested_by else None,
                assigned_to=views.get(p.assigned_to) if p.assigned_to else None,
            )
            for p in proposals
        ]
        return ProposalListPage(items=items, total=total)


@dataclass(slots=True)
class ProposalDetailView:
    proposal: Proposal
    project: CollectionUseProject | None
    conversation_id: str | None
    views: dict[str, PermissionView]

    def view(self, permission_id: PermissionId | None) -> PermissionView | None:
        if permission_id is None:
            return None
        return self.views.get(permission_id)


class GetProposalDetail:
    def __init__(
        self,
        proposal_repository: ProposalRepository,
        project_repository: CollectionUseProjectRepository,
        conversation_repository: ConversationRepository,
        permission_reader: PermissionReader,
    ) -> None:
        self._proposal_repo = proposal_repository
        self._project_repo = project_repository
        self._conversation_repo = conversation_repository
        self._reader = permission_reader

    async def execute(
        self, proposal_id: ProposalId, caller: Actor
    ) -> ProposalDetailView | None:
        proposal = await self._proposal_repo.get_by_id(proposal_id)
        if proposal is None:
            return None
        assert_proposal_access(caller, proposal)
        project = (
            await self._project_repo.get_by_id(proposal.collection_use_project_id)
            if proposal.collection_use_project_id is not None
            else None
        )
        conversation = await self._conversation_repo.get_by_proposal_id(proposal_id)

        permission_ids: list[PermissionId | None] = [
            proposal.requested_by,
            proposal.assigned_to,
            project.requested_by if project else None,
            *(d.submitted_by for d in proposal.documents),
            *(rd.requested_by for rd in proposal.requested_documents),
            *(ro.requested_by for ro in proposal.requested_objects),
        ]
        views = await _resolve_views(self._reader, permission_ids)
        return ProposalDetailView(
            proposal=proposal,
            project=project,
            conversation_id=conversation.id if conversation else None,
            views=views,
        )


# ── Projects ──────────────────────────────────────────────────────────────────


@dataclass(slots=True)
class ProjectListItemView:
    project: CollectionUseProject
    proposal: Proposal | None
    proposal_assigned_to: PermissionView | None
    requested_by: PermissionView | None


@dataclass(slots=True)
class ProjectListPage:
    items: list[ProjectListItemView]
    total: int


class ListProjects:
    def __init__(
        self,
        project_repository: CollectionUseProjectRepository,
        proposal_repository: ProposalRepository,
        permission_reader: PermissionReader,
    ) -> None:
        self._project_repo = project_repository
        self._proposal_repo = proposal_repository
        self._reader = permission_reader

    async def execute(
        self,
        caller: Actor,
        filters: ProjectFilters,
        page: int,
        size: int,
    ) -> ProjectListPage:
        caller_is_staff = is_staff(caller)
        # Gate on the requestedBy filter: staff may scope the list to any
        # requester (e.g. a "my projects" view), but a non-staff caller is
        # always forced to their own id — they cannot widen or spoof the scope.
        if not caller_is_staff:
            filters.requested_by = caller.id
        projects, total = await self._project_repo.list(filters, page, size)

        proposals = await self._proposal_repo.list_by_project_ids(
            [p.id for p in projects]
        )
        proposals_by_project = {
            pr.collection_use_project_id: pr for pr in proposals
        }

        permission_ids: list[PermissionId | None] = [
            pr.assigned_to for pr in proposals
        ]
        if caller_is_staff:
            permission_ids += [p.requested_by for p in projects]
        views = await _resolve_views(self._reader, permission_ids)

        items = []
        for project in projects:
            proposal = proposals_by_project.get(project.id)
            items.append(
                ProjectListItemView(
                    project=project,
                    proposal=proposal,
                    proposal_assigned_to=(
                        views.get(proposal.assigned_to)
                        if proposal and proposal.assigned_to
                        else None
                    ),
                    requested_by=(
                        views.get(project.requested_by) if caller_is_staff else None
                    ),
                )
            )
        return ProjectListPage(items=items, total=total)


@dataclass(slots=True)
class ProjectDetailView:
    project: CollectionUseProject
    proposal: Proposal | None
    proposal_assigned_to: PermissionView | None
    requested_by: PermissionView | None
    authorised_by: PermissionView | None


class GetProjectDetail:
    def __init__(
        self,
        project_repository: CollectionUseProjectRepository,
        proposal_repository: ProposalRepository,
        permission_reader: PermissionReader,
    ) -> None:
        self._project_repo = project_repository
        self._proposal_repo = proposal_repository
        self._reader = permission_reader

    async def execute(
        self, project_id: CollectionUseProjectId, caller: Actor
    ) -> ProjectDetailView | None:
        project = await self._project_repo.get_by_id(project_id)
        if project is None:
            return None
        proposal = await self._proposal_repo.get_by_project_id(project.id)
        assert_project_access(caller, proposal)

        caller_is_staff = is_staff(caller)
        permission_ids: list[PermissionId | None] = [
            proposal.assigned_to if proposal else None
        ]
        if caller_is_staff:
            permission_ids += [project.requested_by, project.authorised_by]
        views = await _resolve_views(self._reader, permission_ids)

        return ProjectDetailView(
            project=project,
            proposal=proposal,
            proposal_assigned_to=(
                views.get(proposal.assigned_to)
                if proposal and proposal.assigned_to
                else None
            ),
            requested_by=(
                views.get(project.requested_by) if caller_is_staff else None
            ),
            authorised_by=(
                views.get(project.authorised_by)
                if caller_is_staff and project.authorised_by
                else None
            ),
        )
