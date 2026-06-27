"""Shared route helpers and the two routers.

Split out of routes.py (HEXAGONAL_UP.md Step 7); shared helpers live in
common.py and composition in dependencies.py. Paths and contracts unchanged.
"""

from __future__ import annotations

import io
import mimetypes
import zipfile

from fastapi import (
    APIRouter,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.identity.public import Actor, GroupName
from app.shared.authorization import (
    STAFF_GROUPS,
)
from app.shared.authorization import (
    is_staff as caller_is_staff,
)
from app.use_of_collections.application.authorization import (
    assert_project_access,
)
from app.use_of_collections.application.ports import (
    CollectionUseProjectRepository,
    ProposalRepository,
)
from app.use_of_collections.domain.models import (
    CollectionUseProjectId,
    Document,
    InsufficientGroup,
    IntendedUse,
    InvalidTransition,
    Message,
    ObjectAccessLog,
    ObjectLogEntry,
    ObjectOccurrenceEntry,
    ObjectOccurrenceLog,
    ObjectReference,
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
    IntendedUseResponse,
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
    UseEventResponse,
    UserSummary,
)

proposals_router = APIRouter(prefix="/proposals", tags=["proposals"])
projects_router = APIRouter(
    prefix="/collection-use-projects", tags=["collection-use-projects"]
)

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
) -> None:
    typed_project_id = CollectionUseProjectId(project_id)
    project = await project_repo.get_by_id(typed_project_id)
    if project is None:
        raise _not_found("project", project_id)
    project_proposal = await _find_project_proposal(typed_project_id, proposal_repo)
    assert_project_access(caller, project_proposal)


def _stub_perm(
    permission_id: str, group: GroupName = GroupName.EXTERNAL
) -> PermissionDetail:
    return PermissionDetail(
        permissionId=permission_id,
        user=UserSummary(id="", name="", email=""),
        group=group,
    )


def _detail_or_none(view: object) -> PermissionDetail | None:
    return permission_detail_from_view(view) if view else None  # type: ignore[arg-type]


def _detail_or_stub(
    view: object,
    permission_id: str,
    group: GroupName = GroupName.EXTERNAL,
) -> PermissionDetail:
    if view:
        return permission_detail_from_view(view)  # type: ignore[arg-type]
    return _stub_perm(permission_id, group)


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


_UPLOAD_CHUNK = 1024 * 1024


async def read_upload_capped(file: UploadFile) -> bytes:
    """Read an upload in chunks, rejecting anything over ``max_upload_bytes``
    (413) before the whole body is buffered."""
    limit = settings.max_upload_bytes
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(_UPLOAD_CHUNK)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail={
                    "error": "FILE_TOO_LARGE",
                    "message": f"File exceeds the {limit}-byte limit",
                },
            )
        chunks.append(chunk)
    return b"".join(chunks)


def ensure_docx(content: bytes) -> None:
    """Reject anything that is not a real DOCX — a ZIP carrying the OOXML
    ``[Content_Types].xml`` part — rather than trusting the file extension."""
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            names = set(archive.namelist())
    except zipfile.BadZipFile:
        names = set()
    if "[Content_Types].xml" not in names:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail={
                "error": "INVALID_FILE_FORMAT",
                "message": "Only valid .docx files are accepted",
            },
        )


def _guess_content_type(file_name: str) -> str:
    """Best-effort MIME type for a download, from the file name's extension.

    Stored `mediaType` is only a coarse category (DOCUMENT/IMAGE/…), not a real
    MIME type, so it can't be used as a Content-Type. Falls back to a generic
    binary type when the extension is unknown."""
    guessed, _ = mimetypes.guess_type(file_name)
    return guessed or "application/octet-stream"


def _intended_use_response(
    intended_use: IntendedUse | None,
) -> IntendedUseResponse | None:
    if intended_use is None:
        return None
    return IntendedUseResponse(
        useType=intended_use.use_type,
        description=intended_use.description,
    )


def _object_reference_response(obj: ObjectReference) -> ObjectReferenceResponse:
    return ObjectReferenceResponse(
        inventoryNumber=obj.inventory_number,
        displayTitle=obj.display_title,
        objectName=obj.object_name,
        briefDescriptionSnapshot=obj.brief_description_snapshot,
    )


async def _build_proposal_event(
    event: ProposalEvent, session: AsyncSession
) -> ProposalEventResponse:
    triggered = await hydrate_permission(event.triggered_by, session) or _stub_perm(
        event.triggered_by
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
    submitted = await hydrate_permission(doc.submitted_by, session) or _stub_perm(
        doc.submitted_by
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
    requested_by = await hydrate_permission(ro.requested_by, session) or _stub_perm(
        ro.requested_by
    )
    return RequestedObjectResponse(
        id=ro.id,
        objectReference=_object_reference_response(ro.object_reference),
        category=ro.category,
        description=ro.description,
        requestedAt=ro.requested_at,
        requestedBy=requested_by,
    )


async def _build_occurrence_entry(
    entry: ObjectOccurrenceEntry, session: AsyncSession
) -> ObjectOccurrenceEntryResponse:
    reported_by = await hydrate_permission(entry.reported_by, session) or _stub_perm(
        entry.reported_by
    )
    return ObjectOccurrenceEntryResponse(
        id=entry.id,
        objectReference=_object_reference_response(entry.object_reference),
        numberOfObjects=entry.number_of_objects,
        occurrenceDate=entry.occurrence_date,
        location=entry.location,
        reportedBy=reported_by,
        detailedDescription=entry.detailed_description,
        testimonial=entry.testimonial,
        requestedObjectId=entry.requested_object_id,
        attachments=[
            AttachmentResponse(
                fileReference=a.file_reference,
                fileName=a.file_name,
                mediaType=a.media_type,
                uploadedAt=a.uploaded_at,
                note=a.note,
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
    entry: PublicationLogEntry, session: AsyncSession
) -> PublicationLogEntryResponse:
    added_by = await hydrate_permission(entry.added_by, session) or _stub_perm(
        entry.added_by
    )
    return PublicationLogEntryResponse(
        id=entry.id,
        addedAt=entry.added_at,
        addedBy=added_by,
        note=entry.note,
        attachments=[
            AttachmentResponse(
                fileReference=a.file_reference,
                fileName=a.file_name,
                mediaType=a.media_type,
                uploadedAt=a.uploaded_at,
                note=a.note,
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
    entry: ObjectLogEntry, session: AsyncSession
) -> ObjectLogEntryResponse:
    added_by = await hydrate_permission(entry.added_by, session) or _stub_perm(
        entry.added_by
    )
    return ObjectLogEntryResponse(
        id=entry.id,
        objectReference=_object_reference_response(entry.object_reference),
        numberOfObjects=entry.number_of_objects,
        addedAt=entry.added_at,
        addedBy=added_by,
        observations=entry.observations,
        requestedObjectId=entry.requested_object_id,
        attachments=[
            AttachmentResponse(
                fileReference=a.file_reference,
                fileName=a.file_name,
                mediaType=a.media_type,
                uploadedAt=a.uploaded_at,
                note=a.note,
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


