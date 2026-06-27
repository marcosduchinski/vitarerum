"""Collection-use project endpoints (lifecycle + events).

Split out of routes.py (HEXAGONAL_UP.md Step 7); shared helpers live in
common.py and composition in dependencies.py. Paths and contracts unchanged.
"""

from __future__ import annotations

import math
from datetime import date
from typing import Annotated

from fastapi import (
    Query,
)

from app.shared.dependencies import CallerPermission
from app.use_of_collections.application.authorization import (
    assert_project_access,
)
from app.use_of_collections.application.ports import (
    ProjectFilters,
)
from app.use_of_collections.application.use_cases import (
    CancelProject,
    CancelProjectInput,
    CompleteProject,
    CompleteProjectInput,
    StartProject,
    StartProjectInput,
)
from app.use_of_collections.domain.enums import (
    UseEventType,
    UseStatus,
    UseType,
)
from app.use_of_collections.domain.models import (
    CollectionUseProjectId,
)
from app.use_of_collections.presentation.common import (
    _assert_existing_project_access,
    _build_use_event,
    _detail_or_none,
    _find_project_proposal,
    _handle_domain_errors,
    _intended_use_response,
    _not_found,
    projects_router,
)
from app.use_of_collections.presentation.dependencies import (
    AccessLogRepo,
    DBSession,
    ListProjectsQuery,
    ProjectDetailQuery,
    ProjectRepo,
    ProposalRepo,
)
from app.use_of_collections.presentation.schemas import (
    CollectionUseObjectResponse,
    NoteRequest,
    PaginatedEventsResponse,
    PaginatedProjectsResponse,
    ProjectCommandResponse,
    ProjectDetailResponse,
    ProjectListItemResponse,
    ProposalRefSummary,
    ReasonRequest,
    UseEventResponse,
)

# ═══════════════════════════════════════════════════════════════════════════════
# Project endpoints
# ═══════════════════════════════════════════════════════════════════════════════


@projects_router.get("", response_model=PaginatedProjectsResponse)
async def list_projects(
    caller: CallerPermission,
    query: ListProjectsQuery,
    status_filter: Annotated[UseStatus | None, Query(alias="status")] = None,
    type_filter: Annotated[UseType | None, Query(alias="type")] = None,
    requested_by: Annotated[str | None, Query(alias="requestedBy")] = None,
    date_from: Annotated[date | None, Query(alias="dateFrom")] = None,
    date_to: Annotated[date | None, Query(alias="dateTo")] = None,
    search: Annotated[str | None, Query()] = None,
    page: Annotated[int, Query(ge=0)] = 0,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PaginatedProjectsResponse:
    # `requestedBy` is honored only for staff; non-staff callers are forced to
    # their own id by ListProjects (they cannot widen or spoof the scope).
    result = await query.execute(
        caller,
        ProjectFilters(
            status=status_filter,
            use_type=type_filter,
            requested_by=requested_by,
            date_from=date_from,
            date_to=date_to,
            search=search,
        ),
        page,
        size,
    )

    items = []
    for item in result.items:
        proposal_ref = None
        if item.proposal:
            proposal_ref = ProposalRefSummary(
                id=item.proposal.id,
                referenceNumber=item.proposal.reference_number.value,
                title=item.proposal.title,
                status=item.proposal.status,
                beginDate=item.proposal.begin_date,
                endDate=item.proposal.end_date,
                submittedAt=item.proposal.submitted_at,
                assignedTo=_detail_or_none(item.proposal_assigned_to),
            )
        items.append(
            ProjectListItemResponse(
                id=item.project.id,
                referenceNumber=item.project.reference_number.value,
                title=item.project.title,
                purpose=item.project.purpose,
                note=item.project.note,
                intendedUse=_intended_use_response(item.project.intended_use),
                status=item.project.status,
                result=item.project.result,
                beginDate=item.project.begin_date,
                endDate=item.project.end_date,
                proposal=proposal_ref,
                requestedBy=_detail_or_none(item.requested_by),
            )
        )

    total = result.total
    return PaginatedProjectsResponse(
        content=items,
        page=page,
        size=size,
        totalElements=total,
        totalPages=math.ceil(total / size) if size > 0 and total > 0 else 0,
    )


@projects_router.get("/{project_id}", response_model=ProjectDetailResponse)
async def get_project(
    project_id: str,
    caller: CallerPermission,
    query: ProjectDetailQuery,
) -> ProjectDetailResponse:
    detail = await query.execute(CollectionUseProjectId(project_id), caller)
    if detail is None:
        raise _not_found("project", project_id)
    project = detail.project

    proposal_ref = None
    if detail.proposal:
        proposal_ref = ProposalRefSummary(
            id=detail.proposal.id,
            referenceNumber=detail.proposal.reference_number.value,
            title=detail.proposal.title,
            status=detail.proposal.status,
            beginDate=detail.proposal.begin_date,
            endDate=detail.proposal.end_date,
            submittedAt=detail.proposal.submitted_at,
            assignedTo=_detail_or_none(detail.proposal_assigned_to),
        )

    authorised_by_detail = _detail_or_none(detail.authorised_by)
    authorised_at = project.authorised_at if authorised_by_detail else None

    return ProjectDetailResponse(
        id=project.id,
        referenceNumber=project.reference_number.value,
        title=project.title,
        purpose=project.purpose,
        note=project.note,
        intendedUse=_intended_use_response(project.intended_use),
        status=project.status,
        result=project.result,
        beginDate=project.begin_date,
        endDate=project.end_date,
        authorisedBy=authorised_by_detail,
        authorisedAt=authorised_at,
        proposal=proposal_ref,
        requestedBy=_detail_or_none(detail.requested_by),
        objects=[
            CollectionUseObjectResponse(
                id=obj.id,
                inventoryNumber=obj.inventory_number,
                displayTitle=obj.display_title,
                objectName=obj.object_name,
                briefDescriptionSnapshot=obj.brief_description_snapshot,
                category=obj.category,
                description=obj.description,
            )
            for obj in project.objects
        ],
    )


def _project_command_response(
    project: object, last_event_resp: UseEventResponse | None
) -> ProjectCommandResponse:
    from app.use_of_collections.domain.models import CollectionUseProject as CUP

    p: CUP = project  # type: ignore[assignment]
    return ProjectCommandResponse(
        id=p.id,
        referenceNumber=p.reference_number.value,
        status=p.status,
        result=p.result,
        lastEvent=last_event_resp,
    )


@projects_router.post("/{project_id}/start", response_model=ProjectCommandResponse)
async def start_project(
    project_id: str,
    body: NoteRequest,
    caller: CallerPermission,
    project_repo: ProjectRepo,
    proposal_repo: ProposalRepo,
    access_log_repo: AccessLogRepo,
    session: DBSession,
) -> ProjectCommandResponse:
    await _assert_existing_project_access(
        project_id, caller, project_repo, proposal_repo
    )
    try:
        project = await StartProject(
            project_repo, access_log_repo
        ).execute(
            StartProjectInput(
                project_id=CollectionUseProjectId(project_id),
                caller=caller,
                note=body.note,
            )
        )
    except Exception as exc:
        _handle_domain_errors(exc)
    await session.commit()
    last_event = (
        await _build_use_event(project.events[-1], session) if project.events else None
    )
    return _project_command_response(project, last_event)


@projects_router.post("/{project_id}/complete", response_model=ProjectCommandResponse)
async def complete_project(
    project_id: str,
    body: NoteRequest,
    caller: CallerPermission,
    project_repo: ProjectRepo,
    proposal_repo: ProposalRepo,
    session: DBSession,
) -> ProjectCommandResponse:
    await _assert_existing_project_access(
        project_id, caller, project_repo, proposal_repo
    )
    try:
        project = await CompleteProject(project_repo).execute(
            CompleteProjectInput(
                project_id=CollectionUseProjectId(project_id),
                caller=caller,
                note=body.note,
            )
        )
    except Exception as exc:
        _handle_domain_errors(exc)
    await session.commit()
    last_event = (
        await _build_use_event(project.events[-1], session) if project.events else None
    )
    return _project_command_response(project, last_event)


@projects_router.post("/{project_id}/cancel", response_model=ProjectCommandResponse)
async def cancel_project(
    project_id: str,
    body: ReasonRequest,
    caller: CallerPermission,
    project_repo: ProjectRepo,
    proposal_repo: ProposalRepo,
    session: DBSession,
) -> ProjectCommandResponse:
    await _assert_existing_project_access(
        project_id, caller, project_repo, proposal_repo
    )
    try:
        project = await CancelProject(project_repo).execute(
            CancelProjectInput(
                project_id=CollectionUseProjectId(project_id),
                caller=caller,
                reason=body.reason,
            )
        )
    except Exception as exc:
        _handle_domain_errors(exc)
    await session.commit()
    last_event = (
        await _build_use_event(project.events[-1], session) if project.events else None
    )
    return _project_command_response(project, last_event)




@projects_router.get(
    "/{project_id}/events",
    response_model=PaginatedEventsResponse,
)
async def list_project_events(
    project_id: str,
    caller: CallerPermission,
    project_repo: ProjectRepo,
    proposal_repo: ProposalRepo,
    session: DBSession,
    type_filter: Annotated[UseEventType | None, Query(alias="type")] = None,
    page: Annotated[int, Query(ge=0)] = 0,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PaginatedEventsResponse:
    project = await project_repo.get_by_id(CollectionUseProjectId(project_id))
    if project is None:
        raise _not_found("project", project_id)
    project_proposal = await _find_project_proposal(
        CollectionUseProjectId(project_id), proposal_repo
    )
    assert_project_access(caller, project_proposal)
    events = project.events
    if type_filter:
        events = [e for e in events if e.type == type_filter]
    events_sorted = sorted(events, key=lambda e: e.occurred_at)
    total = len(events_sorted)
    page_events = events_sorted[page * size : page * size + size]
    items = [await _build_use_event(e, session) for e in page_events]
    return PaginatedEventsResponse(
        projectId=project_id,
        content=items,
        page=page,
        size=size,
        totalElements=total,
        totalPages=math.ceil(total / size) if size > 0 else 0,
    )
