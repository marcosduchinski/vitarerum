"""Collection-use project endpoints (lifecycle + events).

Split out of routes.py (HEXAGONAL_UP.md Step 7); shared helpers live in
common.py and composition in dependencies.py. Paths and contracts unchanged.
"""

from __future__ import annotations

import math
from datetime import date
from typing import Annotated

from fastapi import (
    HTTPException,
    Query,
    Response,
    status,
)

from app.config import settings
from app.shared.authorization import require_staff
from app.shared.dependencies import CallerPermission
from app.use_of_collections.application.authorization import (
    assert_project_access,
)
from app.use_of_collections.application.ports import (
    ProjectFilters,
    StaffProjectTodoPostit,
)
from app.use_of_collections.application.use_cases import (
    AddProjectObjects,
    AddProjectObjectsInput,
    CancelProject,
    CancelProjectInput,
    CompleteProject,
    CompleteProjectInput,
    CompleteStaffProjectTodo,
    CreateFollowUpProject,
    CreateFollowUpProjectInput,
    CreateStaffProjectTodo,
    CreateStaffProjectTodoInput,
    DeleteStaffProjectTodo,
    DeleteStaffProjectTodoInput,
    EditProjectDetails,
    EditProjectDetailsInput,
    ListMyStaffProjectTodoPostits,
    ListMyStaffProjectTodoPostitsInput,
    ListStaffProjectTodos,
    ListStaffProjectTodosInput,
    ProjectObjectHasDependencies,
    ProjectObjectSnapshotInput,
    RemoveProjectObject,
    RemoveProjectObjectCascade,
    RemoveProjectObjectCascadeInput,
    RemoveProjectObjectInput,
    ReopenStaffProjectTodo,
    StartProject,
    StartProjectInput,
    ToggleStaffProjectTodoInput,
    UpdateStaffProjectTodo,
    UpdateStaffProjectTodoInput,
)
from app.use_of_collections.domain.enums import (
    UseEventType,
    UseStatus,
    UseType,
)
from app.use_of_collections.domain.models import (
    CollectionUseObjectId,
    CollectionUseProject,
    CollectionUseProjectId,
    StaffProjectTodoItem,
    StaffProjectTodoItemId,
)
from app.use_of_collections.presentation.common import (
    _assert_existing_project_access,
    _build_use_event,
    _detail_or_none,
    _find_project_proposal,
    _handle_domain_errors,
    _load_permission_detail,
    _not_found,
    projects_router,
    route_now,
)
from app.use_of_collections.presentation.dependencies import (
    AccessLogRepo,
    DBSession,
    FileStorage,
    ListProjectsQuery,
    OccurrenceLogRepo,
    ProjectDetailQuery,
    ProjectRepo,
    ProjectTodoRepo,
    ProposalEmailSender,
    ProposalRepo,
    PublicationLogRepo,
    ReferenceGenerator,
)
from app.use_of_collections.presentation.permissions import hydrate_permission
from app.use_of_collections.presentation.schemas import (
    AddProjectObjectsRequest,
    CollectionUseObjectResponse,
    CreateFollowUpProjectRequest,
    CreateProjectTodoItemRequest,
    NoteRequest,
    PaginatedEventsResponse,
    PaginatedProjectsResponse,
    PermissionDetail,
    ProjectCommandResponse,
    ProjectDetailResponse,
    ProjectListItemResponse,
    ProjectTodoItemResponse,
    ProjectTodoItemsResponse,
    ProjectTodoPostitResponse,
    ProjectTodoPostitsResponse,
    ProposalRefSummary,
    ReasonRequest,
    RemoveProjectObjectRequest,
    UpdateProjectRequest,
    UpdateProjectTodoItemRequest,
    UseEventResponse,
)

# ═══════════════════════════════════════════════════════════════════════════════
# Project endpoints
# ═══════════════════════════════════════════════════════════════════════════════


def _project_link(project_id: CollectionUseProjectId) -> str:
    return f"{settings.public_origin}/p/collections/projects/{project_id}"


def _todo_item_response(item: StaffProjectTodoItem) -> ProjectTodoItemResponse:
    return ProjectTodoItemResponse(
        id=item.id,
        projectId=item.project_id,
        text=item.text,
        completed=item.completed,
        createdAt=item.created_at,
        updatedAt=item.updated_at,
        completedAt=item.completed_at,
        position=item.position,
    )


def _todo_postit_response(item: StaffProjectTodoPostit) -> ProjectTodoPostitResponse:
    return ProjectTodoPostitResponse(
        id=item.id,
        projectId=item.project_id,
        projectReferenceNumber=item.project_reference_number.value,
        projectTitle=item.project_title,
        projectStatus=item.project_status,
        text=item.text,
        completed=item.completed,
        createdAt=item.created_at,
        updatedAt=item.updated_at,
        completedAt=item.completed_at,
        position=item.position,
    )


async def _caller_display_name(caller: CallerPermission, session: DBSession) -> str:
    caller_detail = await hydrate_permission(caller.id, session)
    return caller_detail.user.name if caller_detail else caller.email


async def _project_requester(
    project: CollectionUseProject,
    session: DBSession,
) -> PermissionDetail:
    return await _load_permission_detail(project.requested_by, session)


@projects_router.get("", response_model=PaginatedProjectsResponse)
async def list_projects(
    caller: CallerPermission,
    query: ListProjectsQuery,
    status_filter: Annotated[UseStatus | None, Query(alias="status")] = None,
    type_filter: Annotated[UseType | None, Query(alias="type")] = None,
    requested_by: Annotated[str | None, Query(alias="requestedBy")] = None,
    origin_project_id: Annotated[str | None, Query(alias="originProjectId")] = None,
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
            origin_project_id=(
                CollectionUseProjectId(origin_project_id) if origin_project_id else None
            ),
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
                intendedUse=item.project.intended_use,
                status=item.project.status,
                result=item.project.result,
                beginDate=item.project.begin_date,
                endDate=item.project.end_date,
                originProjectId=item.project.origin_project_id,
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


@projects_router.get("/my-todo-items", response_model=ProjectTodoPostitsResponse)
async def list_my_project_todo_postits(
    caller: CallerPermission,
    todo_repo: ProjectTodoRepo,
    completed: Annotated[bool | None, Query()] = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ProjectTodoPostitsResponse:
    try:
        items = await ListMyStaffProjectTodoPostits(todo_repo).execute(
            ListMyStaffProjectTodoPostitsInput(
                caller=caller,
                completed=completed,
                limit=limit,
            )
        )
    except Exception as exc:
        _handle_domain_errors(exc)
    return ProjectTodoPostitsResponse(
        items=[_todo_postit_response(item) for item in items]
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
        intendedUse=project.intended_use,
        status=project.status,
        result=project.result,
        beginDate=project.begin_date,
        endDate=project.end_date,
        originProjectId=project.origin_project_id,
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
                collectionId=obj.collection_id,
                collectionName=obj.collection_name,
                category=obj.category,
                description=obj.description,
            )
            for obj in project.objects
        ],
    )


@projects_router.get(
    "/{project_id}/todo-items", response_model=ProjectTodoItemsResponse
)
async def list_project_todo_items(
    project_id: str,
    caller: CallerPermission,
    todo_repo: ProjectTodoRepo,
    project_repo: ProjectRepo,
    proposal_repo: ProposalRepo,
) -> ProjectTodoItemsResponse:
    try:
        items = await ListStaffProjectTodos(
            todo_repo, project_repo, proposal_repo
        ).execute(
            ListStaffProjectTodosInput(
                caller=caller,
                project_id=CollectionUseProjectId(project_id),
            )
        )
    except Exception as exc:
        _handle_domain_errors(exc)
    return ProjectTodoItemsResponse(
        projectId=project_id,
        items=[_todo_item_response(item) for item in items],
    )


@projects_router.post(
    "/{project_id}/todo-items",
    response_model=ProjectTodoItemResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_project_todo_item(
    project_id: str,
    body: CreateProjectTodoItemRequest,
    caller: CallerPermission,
    todo_repo: ProjectTodoRepo,
    project_repo: ProjectRepo,
    proposal_repo: ProposalRepo,
    session: DBSession,
) -> ProjectTodoItemResponse:
    try:
        item = await CreateStaffProjectTodo(
            todo_repo, project_repo, proposal_repo
        ).execute(
            CreateStaffProjectTodoInput(
                caller=caller,
                project_id=CollectionUseProjectId(project_id),
                text=body.text,
                now=route_now(),
            )
        )
        await session.commit()
        return _todo_item_response(item)
    except Exception as exc:
        await session.rollback()
        _handle_domain_errors(exc)
        raise RuntimeError("unreachable") from None


@projects_router.patch(
    "/{project_id}/todo-items/{item_id}", response_model=ProjectTodoItemResponse
)
async def update_project_todo_item(
    project_id: str,
    item_id: str,
    body: UpdateProjectTodoItemRequest,
    caller: CallerPermission,
    todo_repo: ProjectTodoRepo,
    project_repo: ProjectRepo,
    proposal_repo: ProposalRepo,
    session: DBSession,
) -> ProjectTodoItemResponse:
    try:
        item = await UpdateStaffProjectTodo(
            todo_repo, project_repo, proposal_repo
        ).execute(
            UpdateStaffProjectTodoInput(
                caller=caller,
                project_id=CollectionUseProjectId(project_id),
                item_id=StaffProjectTodoItemId(item_id),
                now=route_now(),
                text=body.text,
                update_text="text" in body.model_fields_set,
                position=body.position,
                update_position="position" in body.model_fields_set,
            )
        )
        await session.commit()
        return _todo_item_response(item)
    except Exception as exc:
        await session.rollback()
        _handle_domain_errors(exc)
        raise RuntimeError("unreachable") from None


@projects_router.post(
    "/{project_id}/todo-items/{item_id}/complete",
    response_model=ProjectTodoItemResponse,
)
async def complete_project_todo_item(
    project_id: str,
    item_id: str,
    caller: CallerPermission,
    todo_repo: ProjectTodoRepo,
    project_repo: ProjectRepo,
    proposal_repo: ProposalRepo,
    session: DBSession,
) -> ProjectTodoItemResponse:
    try:
        item = await CompleteStaffProjectTodo(
            todo_repo, project_repo, proposal_repo
        ).execute(
            ToggleStaffProjectTodoInput(
                caller=caller,
                project_id=CollectionUseProjectId(project_id),
                item_id=StaffProjectTodoItemId(item_id),
                now=route_now(),
            )
        )
        await session.commit()
        return _todo_item_response(item)
    except Exception as exc:
        await session.rollback()
        _handle_domain_errors(exc)
        raise RuntimeError("unreachable") from None


@projects_router.post(
    "/{project_id}/todo-items/{item_id}/reopen",
    response_model=ProjectTodoItemResponse,
)
async def reopen_project_todo_item(
    project_id: str,
    item_id: str,
    caller: CallerPermission,
    todo_repo: ProjectTodoRepo,
    project_repo: ProjectRepo,
    proposal_repo: ProposalRepo,
    session: DBSession,
) -> ProjectTodoItemResponse:
    try:
        item = await ReopenStaffProjectTodo(
            todo_repo, project_repo, proposal_repo
        ).execute(
            ToggleStaffProjectTodoInput(
                caller=caller,
                project_id=CollectionUseProjectId(project_id),
                item_id=StaffProjectTodoItemId(item_id),
                now=route_now(),
            )
        )
        await session.commit()
        return _todo_item_response(item)
    except Exception as exc:
        await session.rollback()
        _handle_domain_errors(exc)
        raise RuntimeError("unreachable") from None


@projects_router.delete(
    "/{project_id}/todo-items/{item_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_project_todo_item(
    project_id: str,
    item_id: str,
    caller: CallerPermission,
    todo_repo: ProjectTodoRepo,
    project_repo: ProjectRepo,
    proposal_repo: ProposalRepo,
    session: DBSession,
) -> Response:
    try:
        await DeleteStaffProjectTodo(todo_repo, project_repo, proposal_repo).execute(
            DeleteStaffProjectTodoInput(
                caller=caller,
                project_id=CollectionUseProjectId(project_id),
                item_id=StaffProjectTodoItemId(item_id),
            )
        )
        await session.commit()
    except Exception as exc:
        await session.rollback()
        _handle_domain_errors(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@projects_router.patch("/{project_id}", response_model=ProjectDetailResponse)
async def edit_project(
    project_id: str,
    body: UpdateProjectRequest,
    caller: CallerPermission,
    project_repo: ProjectRepo,
    proposal_repo: ProposalRepo,
    detail_query: ProjectDetailQuery,
    session: DBSession,
) -> ProjectDetailResponse:
    project_before = await _assert_existing_project_access(
        project_id, caller, project_repo, proposal_repo
    )
    require_staff(caller)

    fields_set = body.model_fields_set
    update_begin = "beginDate" in fields_set
    update_end = "endDate" in fields_set
    effective_begin = body.beginDate if update_begin else project_before.begin_date
    effective_end = body.endDate if update_end else project_before.end_date
    if (
        effective_begin is not None
        and effective_end is not None
        and effective_end < effective_begin
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "error": "INVALID_DATE_RANGE",
                "message": "endDate must be after beginDate",
            },
        )

    try:
        await EditProjectDetails(project_repo).execute(
            EditProjectDetailsInput(
                project_id=CollectionUseProjectId(project_id),
                caller=caller,
                title=body.title,
                update_title="title" in fields_set,
                purpose=body.purpose,
                update_purpose="purpose" in fields_set,
                begin_date=body.beginDate,
                update_begin_date=update_begin,
                end_date=body.endDate,
                update_end_date=update_end,
            )
        )
    except Exception as exc:
        _handle_domain_errors(exc)
    await session.commit()
    return await get_project(project_id, caller, detail_query)


@projects_router.post(
    "/{project_id}/objects",
    status_code=status.HTTP_201_CREATED,
    response_model=ProjectDetailResponse,
)
async def add_project_objects(
    project_id: str,
    body: AddProjectObjectsRequest,
    caller: CallerPermission,
    project_repo: ProjectRepo,
    proposal_repo: ProposalRepo,
    access_log_repo: AccessLogRepo,
    detail_query: ProjectDetailQuery,
    reference_generator: ReferenceGenerator,
    session: DBSession,
) -> ProjectDetailResponse:
    await _assert_existing_project_access(
        project_id, caller, project_repo, proposal_repo
    )
    require_staff(caller)
    try:
        await AddProjectObjects(
            project_repo, access_log_repo, reference_generator
        ).execute(
            AddProjectObjectsInput(
                project_id=CollectionUseProjectId(project_id),
                caller=caller,
                objects=[
                    ProjectObjectSnapshotInput(
                        inventory_number=obj.inventoryNumber,
                        display_title=obj.displayTitle,
                        object_name=obj.objectName,
                        brief_description_snapshot=obj.briefDescriptionSnapshot,
                        collection_id=obj.collectionId,
                        collection_name=obj.collectionName,
                        category=obj.category,
                        description=obj.description,
                    )
                    for obj in body.objects
                ],
            )
        )
    except Exception as exc:
        _handle_domain_errors(exc)
    await session.commit()
    return await get_project(project_id, caller, detail_query)


@projects_router.post(
    "/{project_id}/follow-ups",
    status_code=status.HTTP_201_CREATED,
    response_model=ProjectDetailResponse,
)
async def create_follow_up_project(
    project_id: str,
    body: CreateFollowUpProjectRequest,
    caller: CallerPermission,
    project_repo: ProjectRepo,
    proposal_repo: ProposalRepo,
    detail_query: ProjectDetailQuery,
    reference_generator: ReferenceGenerator,
    session: DBSession,
) -> ProjectDetailResponse:
    await _assert_existing_project_access(
        project_id, caller, project_repo, proposal_repo
    )
    require_staff(caller)
    try:
        new_project = await CreateFollowUpProject(
            project_repo,
            reference_generator,
        ).execute(
            CreateFollowUpProjectInput(
                origin_project_id=CollectionUseProjectId(project_id),
                caller=caller,
                begin_date=body.beginDate,
                end_date=body.endDate,
                object_ids=[
                    CollectionUseObjectId(object_id) for object_id in body.objectIds
                ],
                title=body.title,
                purpose=body.purpose,
                note=body.note,
            )
        )
    except Exception as exc:
        _handle_domain_errors(exc)
    await session.commit()
    return await get_project(new_project.id, caller, detail_query)


@projects_router.delete(
    "/{project_id}/objects/{object_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_project_object(
    project_id: str,
    object_id: str,
    caller: CallerPermission,
    project_repo: ProjectRepo,
    proposal_repo: ProposalRepo,
    access_log_repo: AccessLogRepo,
    occurrence_log_repo: OccurrenceLogRepo,
    publication_log_repo: PublicationLogRepo,
    session: DBSession,
) -> Response:
    await _assert_existing_project_access(
        project_id, caller, project_repo, proposal_repo
    )
    require_staff(caller)
    try:
        await RemoveProjectObject(
            project_repo,
            access_log_repo,
            occurrence_log_repo,
            publication_log_repo,
        ).execute(
            RemoveProjectObjectInput(
                project_id=CollectionUseProjectId(project_id),
                collection_use_object_id=CollectionUseObjectId(object_id),
                caller=caller,
            )
        )
    except ProjectObjectHasDependencies as exc:
        _raise_project_object_has_dependencies(exc)
    except Exception as exc:
        _handle_domain_errors(exc)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@projects_router.post(
    "/{project_id}/objects/{object_id}/remove",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_project_object_cascade(
    project_id: str,
    object_id: str,
    body: RemoveProjectObjectRequest,
    caller: CallerPermission,
    project_repo: ProjectRepo,
    proposal_repo: ProposalRepo,
    access_log_repo: AccessLogRepo,
    occurrence_log_repo: OccurrenceLogRepo,
    publication_log_repo: PublicationLogRepo,
    file_storage: FileStorage,
    session: DBSession,
) -> Response:
    await _assert_existing_project_access(
        project_id, caller, project_repo, proposal_repo
    )
    require_staff(caller)
    try:
        await RemoveProjectObjectCascade(
            project_repo,
            access_log_repo,
            occurrence_log_repo,
            publication_log_repo,
            file_storage,
        ).execute(
            RemoveProjectObjectCascadeInput(
                project_id=CollectionUseProjectId(project_id),
                collection_use_object_id=CollectionUseObjectId(object_id),
                caller=caller,
                reason=body.reason,
                confirm_cascade=body.confirmCascade,
            )
        )
    except Exception as exc:
        _handle_domain_errors(exc)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _raise_project_object_has_dependencies(
    exc: ProjectObjectHasDependencies,
) -> None:
    summary = exc.summary
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "error": "PROJECT_OBJECT_HAS_DEPENDENCIES",
            "message": str(exc),
            "dependencies": {
                "accessLogEntries": summary.access_log_entries,
                "occurrenceEntries": summary.occurrence_entries,
                "publicationEntries": summary.publication_entries,
                "attachments": summary.attachments,
            },
        },
    ) from exc


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
    reference_generator: ReferenceGenerator,
    proposal_notification_email_sender: ProposalEmailSender,
    session: DBSession,
) -> ProjectCommandResponse:
    await _assert_existing_project_access(
        project_id, caller, project_repo, proposal_repo
    )
    try:
        project = await StartProject(
            project_repo, access_log_repo, reference_generator
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
    requester = await _project_requester(project, session)
    await proposal_notification_email_sender.send_project_started(
        to_email=requester.user.email,
        requester_name=requester.user.name,
        project_reference=project.reference_number.value,
        started_by_name=await _caller_display_name(caller, session),
        link=_project_link(project.id),
    )
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
    proposal_notification_email_sender: ProposalEmailSender,
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
    requester = await _project_requester(project, session)
    await proposal_notification_email_sender.send_project_completed(
        to_email=requester.user.email,
        requester_name=requester.user.name,
        project_reference=project.reference_number.value,
        completed_by_name=await _caller_display_name(caller, session),
        link=_project_link(project.id),
    )
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
    proposal_notification_email_sender: ProposalEmailSender,
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
    requester = await _project_requester(project, session)
    await proposal_notification_email_sender.send_project_cancelled(
        to_email=requester.user.email,
        requester_name=requester.user.name,
        project_reference=project.reference_number.value,
        cancelled_by_name=await _caller_display_name(caller, session),
        reason=body.reason,
        link=_project_link(project.id),
    )
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
    assert_project_access(caller, project, project_proposal)
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
