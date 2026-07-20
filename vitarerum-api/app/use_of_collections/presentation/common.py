"""Shared route helpers and the two routers.

Split out of routes.py (HEXAGONAL_UP.md Step 7); shared helpers live in
common.py and composition in dependencies.py. Paths and contracts unchanged.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import (
    APIRouter,
    HTTPException,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.identity.public import Actor, GroupName
from app.shared.authorization import (
    STAFF_GROUPS,
)
from app.shared.authorization import (
    is_staff as caller_is_staff,
)
from app.shared.uploads import (
    ensure_docx as ensure_docx,
)
from app.shared.uploads import (
    guess_content_type,
    safe_basename,
)
from app.shared.uploads import (
    read_upload_capped as read_upload_capped,
)
from app.use_of_collections.application.authorization import (
    assert_project_access,
)
from app.use_of_collections.application.ports import (
    CollectionUseProjectRepository,
    ProposalRepository,
)
from app.use_of_collections.domain.models import (
    CollectionUseObject,
    CollectionUseObjectId,
    CollectionUseProject,
    CollectionUseProjectId,
    Document,
    InsufficientGroup,
    InvalidTransition,
    Message,
    ObjectAccessLog,
    ObjectLogEntry,
    ObjectOccurrenceEntry,
    ObjectOccurrenceLog,
    PermissionId,
    Proposal,
    ProposalEvent,
    PublicationLog,
    PublicationLogEntry,
    RequestedObject,
    UseEvent,
)
from app.use_of_collections.presentation.permissions import (
    hydrate_permission,
    hydrate_permission_or_stub,
    permission_detail_from_view,
)
from app.use_of_collections.presentation.schemas import (
    AttachmentResponse,
    DocumentResponse,
    MessageAttachmentResponse,
    MessageResponse,
    ObjectAccessLogResponse,
    ObjectLogEntryResponse,
    ObjectOccurrenceEntryResponse,
    ObjectOccurrenceLogResponse,
    ObjectReferenceResponse,
    PermissionDetail,
    ProposalEventResponse,
    PublicationLogEntryResponse,
    PublicationLogResponse,
    RequestedObjectResponse,
    RequesterContactResponse,
    UseEventResponse,
    UserSummary,
)

proposals_router = APIRouter(prefix="/proposals", tags=["proposals"])
projects_router = APIRouter(
    prefix="/collection-use-projects", tags=["collection-use-projects"]
)


def route_now() -> datetime:
    return datetime.now(UTC)


def route_new_id() -> str:
    return str(uuid4())


def route_file_reference(subdir: str, owner_id: str, file_name: str) -> str:
    return f"{subdir}/{owner_id}/{route_new_id()}_{safe_basename(file_name)}"


def _is_staff(caller: Actor) -> bool:
    return caller_is_staff(caller)


async def _find_project_proposal(
    project_id: CollectionUseProjectId,
    proposal_repo: ProposalRepository,
) -> Proposal | None:
    return await proposal_repo.get_by_project_id(project_id)


async def _assert_existing_project_access(
    project_id: str,
    caller: Actor,
    project_repo: CollectionUseProjectRepository,
    proposal_repo: ProposalRepository,
) -> CollectionUseProject:
    typed_project_id = CollectionUseProjectId(project_id)
    project = await project_repo.get_by_id(typed_project_id)
    if project is None:
        raise _not_found("project", project_id)
    project_proposal = await _find_project_proposal(typed_project_id, proposal_repo)
    assert_project_access(caller, project_proposal)
    return project


def _collection_use_objects_by_id(
    project: CollectionUseProject,
) -> dict[CollectionUseObjectId, CollectionUseObject]:
    return {obj.id: obj for obj in project.objects}


def _object_reference_response(obj: CollectionUseObject) -> ObjectReferenceResponse:
    return ObjectReferenceResponse(
        inventoryNumber=obj.inventory_number,
        displayTitle=obj.display_title,
        objectName=obj.object_name,
        briefDescriptionSnapshot=obj.brief_description_snapshot,
    )


def _stub_perm(
    permission_id: str, group: GroupName = GroupName.EXTERNAL
) -> PermissionDetail:
    return PermissionDetail(
        permissionId=permission_id,
        user=UserSummary(id="", name="", email=""),
        group=group,
    )


def _detail_or_none(view: object) -> PermissionDetail | None:
    if not view:
        return None
    if isinstance(view, PermissionDetail):
        return view
    return permission_detail_from_view(view)  # type: ignore[arg-type]


def _detail_or_stub(
    view: object,
    permission_id: str,
    group: GroupName = GroupName.EXTERNAL,
) -> PermissionDetail:
    return _detail_or_none(view) or _stub_perm(permission_id, group)


def _detail_or_stub_or_none(
    view: object,
    permission_id: str | None,
    group: GroupName = GroupName.EXTERNAL,
) -> PermissionDetail | None:
    if permission_id is None:
        return None
    return _detail_or_stub(view, permission_id, group)


def _requester_contact_response(
    proposal: Proposal,
) -> RequesterContactResponse | None:
    if proposal.requester_contact is None:
        return None
    return RequesterContactResponse(
        name=proposal.requester_contact.name,
        email=proposal.requester_contact.email.value,
    )


async def _load_permission_detail(
    permission_id: PermissionId,
    session: AsyncSession,
) -> PermissionDetail:
    detail = await hydrate_permission_or_stub(permission_id, session)
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "PERMISSION_NOT_FOUND",
                "message": f"No permission found with id {permission_id}",
            },
        )
    return detail


async def _require_staff_permission_target(
    permission_id: PermissionId,
    session: AsyncSession,
) -> PermissionDetail:
    detail = await _load_permission_detail(permission_id, session)
    if detail.group not in STAFF_GROUPS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "error": "INVALID_PERMISSION_TARGET",
                "message": "Target permission must belong to a staff group",
            },
        )
    return detail


def _handle_domain_errors(exc: Exception) -> None:
    # InvalidTransition subclasses ValueError — it must be matched first to
    # produce the 409 INVALID_TRANSITION promised by the API contracts.
    if isinstance(exc, InvalidTransition):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "INVALID_TRANSITION", "message": str(exc)},
        )
    if isinstance(exc, ValueError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"error": "VALIDATION_ERROR", "message": str(exc)},
        )
    if isinstance(exc, InsufficientGroup):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "INSUFFICIENT_GROUP", "message": str(exc)},
        )
    if isinstance(exc, PermissionError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "ACCESS_DENIED", "message": str(exc)},
        )
    if isinstance(exc, LookupError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "NOT_FOUND", "message": str(exc)},
        )
    raise exc


def _not_found(resource: str, resource_id: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "error": f"{resource.upper()}_NOT_FOUND",
            "message": f"No {resource} found with id {resource_id}",
        },
    )


# Upload/download helpers live in the shared layer so other bounded contexts can
# reuse them; kept re-exported here for existing call sites in this context.
_guess_content_type = guess_content_type


async def _build_proposal_event(
    event: ProposalEvent, session: AsyncSession
) -> ProposalEventResponse:
    triggered = _detail_or_stub_or_none(
        await hydrate_permission_or_stub(event.triggered_by, session),
        event.triggered_by,
    )
    return ProposalEventResponse(
        occurredAt=event.occurred_at,
        type=event.type,
        triggeredBy=triggered,
        note=event.note,
    )


async def _build_use_event(event: UseEvent, session: AsyncSession) -> UseEventResponse:
    triggered = await hydrate_permission(event.triggered_by, session) or _stub_perm(
        event.triggered_by
    )
    return UseEventResponse(
        occurredAt=event.occurred_at,
        type=event.type,
        triggeredBy=triggered,
        note=event.note,
    )


async def _build_document_response(
    doc: Document, session: AsyncSession
) -> DocumentResponse:
    submitted = _detail_or_stub_or_none(
        await hydrate_permission_or_stub(doc.submitted_by, session),
        doc.submitted_by,
    )
    return DocumentResponse(
        id=doc.id,
        type=doc.type.value,
        fileName=doc.file_name,
        fileReference=doc.file_reference,
        submittedAt=doc.submitted_at,
        submittedBy=submitted,
    )


async def _build_requested_object(
    ro: RequestedObject, session: AsyncSession
) -> RequestedObjectResponse:
    requested_by = (
        (await hydrate_permission(ro.requested_by, session))
        or _stub_perm(ro.requested_by)
        if ro.requested_by is not None
        else None
    )
    return RequestedObjectResponse(
        id=ro.id,
        inventoryNumber=ro.inventory_number,
        displayTitle=ro.display_title,
        objectName=ro.object_name,
        briefDescriptionSnapshot=ro.brief_description_snapshot,
        category=ro.category,
        description=ro.description,
        requestedAt=ro.requested_at,
        requestedBy=requested_by,
    )


async def _build_occurrence_entry(
    entry: ObjectOccurrenceEntry,
    session: AsyncSession,
    collection_use_object: CollectionUseObject,
) -> ObjectOccurrenceEntryResponse:
    reported_by = await hydrate_permission(entry.reported_by, session) or _stub_perm(
        entry.reported_by
    )
    return ObjectOccurrenceEntryResponse(
        id=entry.id,
        collectionUseObjectId=entry.collection_use_object_id,
        objectReference=_object_reference_response(collection_use_object),
        numberOfObjects=entry.number_of_objects,
        occurrenceDate=entry.occurrence_date,
        location=entry.location,
        reportedBy=reported_by,
        detailedDescription=entry.detailed_description,
        testimonial=entry.testimonial,
        attachments=[
            AttachmentResponse(
                fileReference=a.file_reference,
                fileName=a.file_name,
                mediaType=a.media_type,
                uploadedAt=a.uploaded_at,
                attachmentDescription=a.description,
            )
            for a in entry.attachments
        ],
    )


async def _build_occurrence_log_response(
    occurrence_log: ObjectOccurrenceLog, session: AsyncSession
) -> ObjectOccurrenceLogResponse:
    curator = (
        await hydrate_permission(occurrence_log.curator, session)
        or _stub_perm(occurrence_log.curator)
        if occurrence_log.curator
        else None
    )
    return ObjectOccurrenceLogResponse(
        id=occurrence_log.id,
        referenceNumber=occurrence_log.reference_number.value,
        projectId=occurrence_log.collection_use_project_id,
        dateConclusion=occurrence_log.date_conclusion,
        curator=curator,
    )


async def _build_publication_entry(
    entry: PublicationLogEntry,
    session: AsyncSession,
    collection_use_object: CollectionUseObject | None = None,
) -> PublicationLogEntryResponse:
    added_by = await hydrate_permission(entry.added_by, session) or _stub_perm(
        entry.added_by
    )
    return PublicationLogEntryResponse(
        id=entry.id,
        addedAt=entry.added_at,
        addedBy=added_by,
        note=entry.note,
        collectionUseObjectId=entry.collection_use_object_id,
        objectReference=(
            _object_reference_response(collection_use_object)
            if collection_use_object is not None
            else None
        ),
        attachments=[
            AttachmentResponse(
                fileReference=a.file_reference,
                fileName=a.file_name,
                mediaType=a.media_type,
                uploadedAt=a.uploaded_at,
                attachmentDescription=a.description,
            )
            for a in entry.attachments
        ],
    )


async def _build_publication_log_response(
    publication_log: PublicationLog, session: AsyncSession
) -> PublicationLogResponse:
    curator = (
        await hydrate_permission(publication_log.curator, session)
        or _stub_perm(publication_log.curator)
        if publication_log.curator
        else None
    )
    return PublicationLogResponse(
        id=publication_log.id,
        referenceNumber=publication_log.reference_number.value,
        projectId=publication_log.collection_use_project_id,
        curator=curator,
    )


async def _build_object_log_entry(
    entry: ObjectLogEntry,
    session: AsyncSession,
    collection_use_object: CollectionUseObject,
) -> ObjectLogEntryResponse:
    added_by = await hydrate_permission(entry.added_by, session) or _stub_perm(
        entry.added_by
    )
    return ObjectLogEntryResponse(
        id=entry.id,
        collectionUseObjectId=entry.collection_use_object_id,
        objectReference=_object_reference_response(collection_use_object),
        numberOfObjects=entry.number_of_objects,
        addedAt=entry.added_at,
        addedBy=added_by,
        observations=entry.observations,
        attachments=[
            AttachmentResponse(
                fileReference=a.file_reference,
                fileName=a.file_name,
                mediaType=a.media_type,
                uploadedAt=a.uploaded_at,
                attachmentDescription=a.description,
            )
            for a in entry.attachments
        ],
    )


async def _build_access_log_response(
    access_log: ObjectAccessLog, session: AsyncSession
) -> ObjectAccessLogResponse:
    curator = (
        await hydrate_permission(access_log.curator, session)
        or _stub_perm(access_log.curator)
        if access_log.curator
        else None
    )
    return ObjectAccessLogResponse(
        id=access_log.id,
        referenceNumber=access_log.reference_number.value,
        projectId=access_log.collection_use_project_id,
        dateConclusion=access_log.date_conclusion,
        curator=curator,
    )


def _message_response(message: Message) -> MessageResponse:
    return MessageResponse(
        id=message.id,
        sentAt=message.sent_at,
        sender=message.sender.value,
        recipient=message.recipient.value,
        subject=message.subject,
        body=message.body,
        attachments=[
            MessageAttachmentResponse(
                documentId=att.document_id, fileName=att.file_name
            )
            for att in message.attachments
        ],
    )
