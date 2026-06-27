"""Journal endpoints: object access log and object occurrence log.

Split out of routes.py (HEXAGONAL_UP.md Step 7); shared helpers live in
common.py and composition in dependencies.py. Paths and contracts unchanged.
"""

from __future__ import annotations

import math
from typing import Annotated

from fastapi import (
    File,
    Form,
    Query,
    Response,
    UploadFile,
    status,
)

from app.shared.dependencies import CallerPermission
from app.use_of_collections.application.use_cases import (
    AddLogEntryAttachment,
    AddLogEntryAttachmentInput,
    AddObjectLogEntry,
    AddObjectLogEntryInput,
    AddObjectOccurrenceEntry,
    AddObjectOccurrenceEntryInput,
    AddOccurrenceEntryAttachment,
    AddOccurrenceEntryAttachmentInput,
    AddPublicationEntryAttachment,
    AddPublicationEntryAttachmentInput,
    AddPublicationLogEntry,
    AddPublicationLogEntryInput,
    EditObjectLogEntry,
    EditObjectLogEntryInput,
    EditObjectOccurrenceEntry,
    EditObjectOccurrenceEntryInput,
    EditPublicationLogEntry,
    EditPublicationLogEntryInput,
    GetObjectAccessLog,
    GetObjectAccessLogInput,
    GetObjectOccurrenceLog,
    GetObjectOccurrenceLogInput,
    GetPublicationLog,
    GetPublicationLogInput,
)
from app.use_of_collections.domain.models import (
    Attachment,
    CollectionUseObjectId,
    CollectionUseProjectId,
    InvalidTransition,
    ObjectLogEntryId,
    ObjectOccurrenceEntryId,
    PublicationLogEntryId,
)
from app.use_of_collections.presentation.common import (
    _assert_existing_project_access,
    _build_access_log_response,
    _build_object_log_entry,
    _build_occurrence_entry,
    _build_occurrence_log_response,
    _build_publication_entry,
    _build_publication_log_response,
    _guess_content_type,
    _handle_domain_errors,
    _is_staff,
    _not_found,
    projects_router,
    read_upload_capped,
)
from app.use_of_collections.presentation.dependencies import (
    AccessLogRepo,
    DBSession,
    FileStorage,
    OccurrenceLogRepo,
    ProjectRepo,
    ProposalRepo,
    PublicationLogRepo,
)
from app.use_of_collections.presentation.schemas import (
    AddLogEntryRequest,
    AddOccurrenceEntryRequest,
    AddPublicationEntryRequest,
    AttachmentResponse,
    EditLogEntryRequest,
    EditOccurrenceEntryRequest,
    EditPublicationEntryRequest,
    ObjectAccessLogResponse,
    ObjectLogEntryResponse,
    ObjectOccurrenceEntryResponse,
    ObjectOccurrenceLogResponse,
    PaginatedLogEntriesResponse,
    PaginatedOccurrenceEntriesResponse,
    PaginatedPublicationEntriesResponse,
    PublicationLogEntryResponse,
    PublicationLogResponse,
)


async def _download_attachment(
    attachments: list[Attachment],
    file_reference: str,
    file_storage: FileStorage,
) -> Response:
    attachment = next(
        (a for a in attachments if a.file_reference == file_reference), None
    )
    if attachment is None:
        raise _not_found("attachment", file_reference)
    try:
        content = await file_storage.read(attachment.file_reference)
    except FileNotFoundError as exc:
        raise _not_found("attachment", file_reference) from exc
    return Response(
        content=content,
        media_type=_guess_content_type(attachment.file_name),
        headers={
            "Content-Disposition": f'attachment; filename="{attachment.file_name}"'
        },
    )


# ── Object log entries ─────────────────────────────────────────────────────--


@projects_router.post(
    "/{project_id}/log-entries",
    status_code=status.HTTP_201_CREATED,
    response_model=ObjectLogEntryResponse,
)
async def add_log_entry(
    project_id: str,
    body: AddLogEntryRequest,
    caller: CallerPermission,
    project_repo: ProjectRepo,
    proposal_repo: ProposalRepo,
    access_log_repo: AccessLogRepo,
    session: DBSession,
) -> ObjectLogEntryResponse:
    await _assert_existing_project_access(
        project_id, caller, project_repo, proposal_repo
    )
    try:
        entry = await AddObjectLogEntry(project_repo, access_log_repo).execute(
            AddObjectLogEntryInput(
                project_id=CollectionUseProjectId(project_id),
                caller=caller,
                collection_use_object_id=CollectionUseObjectId(
                    body.collectionUseObjectId
                ),
                number_of_objects=body.numberOfObjects,
                observations=body.observations,
                restrict_to_in_progress=not _is_staff(caller),
            )
        )
    except Exception as exc:
        _handle_domain_errors(exc)
    await session.commit()
    return await _build_object_log_entry(entry, session)


@projects_router.patch(
    "/{project_id}/log-entries/{entry_id}",
    response_model=ObjectLogEntryResponse,
)
async def edit_log_entry(
    project_id: str,
    entry_id: str,
    body: EditLogEntryRequest,
    caller: CallerPermission,
    project_repo: ProjectRepo,
    proposal_repo: ProposalRepo,
    access_log_repo: AccessLogRepo,
    session: DBSession,
) -> ObjectLogEntryResponse:
    await _assert_existing_project_access(
        project_id, caller, project_repo, proposal_repo
    )
    try:
        entry = await EditObjectLogEntry(project_repo, access_log_repo).execute(
            EditObjectLogEntryInput(
                project_id=CollectionUseProjectId(project_id),
                entry_id=ObjectLogEntryId(entry_id),
                caller=caller,
                added_at=body.addedAt,
                number_of_objects=body.numberOfObjects,
                observations=body.observations,
                update_observations="observations" in body.model_fields_set,
                restrict_to_in_progress=not _is_staff(caller),
            )
        )
    except (InvalidTransition, ValueError) as exc:
        _handle_domain_errors(exc)
    except LookupError as exc:
        raise _not_found("entry", entry_id) from exc
    await session.commit()
    return await _build_object_log_entry(entry, session)


@projects_router.get(
    "/{project_id}/log-entries",
    response_model=PaginatedLogEntriesResponse,
)
async def list_log_entries(
    project_id: str,
    caller: CallerPermission,
    project_repo: ProjectRepo,
    proposal_repo: ProposalRepo,
    access_log_repo: AccessLogRepo,
    session: DBSession,
    added_by: Annotated[str | None, Query()] = None,
    page: Annotated[int, Query(ge=0)] = 0,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PaginatedLogEntriesResponse:
    await _assert_existing_project_access(
        project_id, caller, project_repo, proposal_repo
    )
    access_log = await access_log_repo.get_by_project_id(
        CollectionUseProjectId(project_id)
    )
    entries, total = await access_log_repo.list_entries_by_project(
        CollectionUseProjectId(project_id), added_by, page, size
    )
    items = [await _build_object_log_entry(e, session) for e in entries]
    return PaginatedLogEntriesResponse(
        projectId=project_id,
        accessLog=(
            await _build_access_log_response(access_log, session)
            if access_log
            else None
        ),
        content=items,
        page=page,
        size=size,
        totalElements=total,
        totalPages=math.ceil(total / size) if size > 0 else 0,
    )


@projects_router.get(
    "/{project_id}/object-access-log",
    response_model=ObjectAccessLogResponse,
)
async def get_object_access_log(
    project_id: str,
    caller: CallerPermission,
    project_repo: ProjectRepo,
    proposal_repo: ProposalRepo,
    access_log_repo: AccessLogRepo,
    session: DBSession,
) -> ObjectAccessLogResponse:
    await _assert_existing_project_access(
        project_id, caller, project_repo, proposal_repo
    )
    access_log = await GetObjectAccessLog(project_repo, access_log_repo).execute(
        GetObjectAccessLogInput(project_id=CollectionUseProjectId(project_id))
    )
    if access_log is None:
        raise _not_found("object_access_log", project_id)
    return await _build_access_log_response(access_log, session)


@projects_router.post(
    "/{project_id}/log-entries/{entry_id}/attachments",
    status_code=status.HTTP_201_CREATED,
    response_model=AttachmentResponse,
)
async def add_log_entry_attachment(
    project_id: str,
    entry_id: str,
    caller: CallerPermission,
    project_repo: ProjectRepo,
    proposal_repo: ProposalRepo,
    access_log_repo: AccessLogRepo,
    file_storage: FileStorage,
    session: DBSession,
    file: Annotated[UploadFile, File(...)],
    mediaType: Annotated[str, Form(...)],
    note: Annotated[str | None, Form()] = None,
) -> AttachmentResponse:
    await _assert_existing_project_access(
        project_id, caller, project_repo, proposal_repo
    )
    content = await read_upload_capped(file)
    try:
        attachment = await AddLogEntryAttachment(
            project_repo, access_log_repo, file_storage
        ).execute(
            AddLogEntryAttachmentInput(
                project_id=CollectionUseProjectId(project_id),
                entry_id=ObjectLogEntryId(entry_id),
                caller=caller,
                file_content=content,
                file_name=file.filename or "upload",
                media_type=mediaType,
                note=note,
                restrict_to_in_progress=not _is_staff(caller),
            )
        )
    except (InvalidTransition, ValueError) as exc:
        _handle_domain_errors(exc)
    except LookupError as exc:
        raise _not_found("entry", entry_id) from exc
    await session.commit()
    return AttachmentResponse(
        fileReference=attachment.file_reference,
        fileName=attachment.file_name,
        mediaType=attachment.media_type,
        uploadedAt=attachment.uploaded_at,
        note=attachment.note,
    )


@projects_router.get(
    "/{project_id}/log-entries/{entry_id}/attachments/{file_reference:path}",
)
async def download_log_entry_attachment(
    project_id: str,
    entry_id: str,
    file_reference: str,
    caller: CallerPermission,
    project_repo: ProjectRepo,
    proposal_repo: ProposalRepo,
    access_log_repo: AccessLogRepo,
    file_storage: FileStorage,
) -> Response:
    await _assert_existing_project_access(
        project_id, caller, project_repo, proposal_repo
    )
    entry = await access_log_repo.get_entry_by_id(ObjectLogEntryId(entry_id))
    if entry is None:
        raise _not_found("entry", entry_id)
    access_log = await access_log_repo.get_by_id(entry.object_access_log_id)
    if access_log is None or access_log.collection_use_project_id != (
        CollectionUseProjectId(project_id)
    ):
        raise _not_found("entry", entry_id)
    return await _download_attachment(entry.attachments, file_reference, file_storage)


# ── Object occurrence entries ──────────────────────────────────────────────--


@projects_router.post(
    "/{project_id}/occurrence-entries",
    status_code=status.HTTP_201_CREATED,
    response_model=ObjectOccurrenceEntryResponse,
)
async def add_occurrence_entry(
    project_id: str,
    body: AddOccurrenceEntryRequest,
    caller: CallerPermission,
    project_repo: ProjectRepo,
    proposal_repo: ProposalRepo,
    occurrence_log_repo: OccurrenceLogRepo,
    session: DBSession,
) -> ObjectOccurrenceEntryResponse:
    await _assert_existing_project_access(
        project_id, caller, project_repo, proposal_repo
    )
    try:
        entry = await AddObjectOccurrenceEntry(
            project_repo, occurrence_log_repo
        ).execute(
            AddObjectOccurrenceEntryInput(
                project_id=CollectionUseProjectId(project_id),
                caller=caller,
                collection_use_object_id=CollectionUseObjectId(
                    body.collectionUseObjectId
                ),
                number_of_objects=body.numberOfObjects,
                occurrence_date=body.occurrenceDate,
                location=body.location,
                detailed_description=body.detailedDescription,
                testimonial=body.testimonial,
                restrict_to_in_progress=not _is_staff(caller),
            )
        )
    except Exception as exc:
        _handle_domain_errors(exc)
    await session.commit()
    return await _build_occurrence_entry(entry, session)


@projects_router.patch(
    "/{project_id}/occurrence-entries/{entry_id}",
    response_model=ObjectOccurrenceEntryResponse,
)
async def edit_occurrence_entry(
    project_id: str,
    entry_id: str,
    body: EditOccurrenceEntryRequest,
    caller: CallerPermission,
    project_repo: ProjectRepo,
    proposal_repo: ProposalRepo,
    occurrence_log_repo: OccurrenceLogRepo,
    session: DBSession,
) -> ObjectOccurrenceEntryResponse:
    await _assert_existing_project_access(
        project_id, caller, project_repo, proposal_repo
    )
    try:
        entry = await EditObjectOccurrenceEntry(
            project_repo, occurrence_log_repo
        ).execute(
            EditObjectOccurrenceEntryInput(
                project_id=CollectionUseProjectId(project_id),
                entry_id=ObjectOccurrenceEntryId(entry_id),
                caller=caller,
                number_of_objects=body.numberOfObjects,
                occurrence_date=body.occurrenceDate,
                location=body.location,
                detailed_description=body.detailedDescription,
                testimonial=body.testimonial,
                update_testimonial="testimonial" in body.model_fields_set,
                restrict_to_in_progress=not _is_staff(caller),
            )
        )
    except (InvalidTransition, ValueError) as exc:
        _handle_domain_errors(exc)
    except LookupError as exc:
        raise _not_found("entry", entry_id) from exc
    await session.commit()
    return await _build_occurrence_entry(entry, session)


@projects_router.get(
    "/{project_id}/occurrence-entries",
    response_model=PaginatedOccurrenceEntriesResponse,
)
async def list_occurrence_entries(
    project_id: str,
    caller: CallerPermission,
    project_repo: ProjectRepo,
    proposal_repo: ProposalRepo,
    occurrence_log_repo: OccurrenceLogRepo,
    session: DBSession,
    reported_by: Annotated[str | None, Query(alias="reportedBy")] = None,
    page: Annotated[int, Query(ge=0)] = 0,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PaginatedOccurrenceEntriesResponse:
    await _assert_existing_project_access(
        project_id, caller, project_repo, proposal_repo
    )
    occurrence_log = await occurrence_log_repo.get_by_project_id(
        CollectionUseProjectId(project_id)
    )
    entries, total = await occurrence_log_repo.list_entries_by_project(
        CollectionUseProjectId(project_id), reported_by, page, size
    )
    items = [await _build_occurrence_entry(e, session) for e in entries]
    return PaginatedOccurrenceEntriesResponse(
        projectId=project_id,
        occurrenceLog=(
            await _build_occurrence_log_response(occurrence_log, session)
            if occurrence_log
            else None
        ),
        content=items,
        page=page,
        size=size,
        totalElements=total,
        totalPages=math.ceil(total / size) if size > 0 else 0,
    )


@projects_router.get(
    "/{project_id}/object-occurrence-log",
    response_model=ObjectOccurrenceLogResponse,
)
async def get_object_occurrence_log(
    project_id: str,
    caller: CallerPermission,
    project_repo: ProjectRepo,
    proposal_repo: ProposalRepo,
    occurrence_log_repo: OccurrenceLogRepo,
    session: DBSession,
) -> ObjectOccurrenceLogResponse:
    await _assert_existing_project_access(
        project_id, caller, project_repo, proposal_repo
    )
    occurrence_log = await GetObjectOccurrenceLog(
        project_repo, occurrence_log_repo
    ).execute(GetObjectOccurrenceLogInput(project_id=CollectionUseProjectId(project_id)))
    if occurrence_log is None:
        raise _not_found("object_occurrence_log", project_id)
    return await _build_occurrence_log_response(occurrence_log, session)


@projects_router.post(
    "/{project_id}/occurrence-entries/{entry_id}/attachments",
    status_code=status.HTTP_201_CREATED,
    response_model=AttachmentResponse,
)
async def add_occurrence_entry_attachment(
    project_id: str,
    entry_id: str,
    caller: CallerPermission,
    project_repo: ProjectRepo,
    proposal_repo: ProposalRepo,
    occurrence_log_repo: OccurrenceLogRepo,
    file_storage: FileStorage,
    session: DBSession,
    file: Annotated[UploadFile, File(...)],
    mediaType: Annotated[str, Form(...)],
    note: Annotated[str | None, Form()] = None,
) -> AttachmentResponse:
    await _assert_existing_project_access(
        project_id, caller, project_repo, proposal_repo
    )
    content = await read_upload_capped(file)
    try:
        attachment = await AddOccurrenceEntryAttachment(
            project_repo, occurrence_log_repo, file_storage
        ).execute(
            AddOccurrenceEntryAttachmentInput(
                project_id=CollectionUseProjectId(project_id),
                entry_id=ObjectOccurrenceEntryId(entry_id),
                caller=caller,
                file_content=content,
                file_name=file.filename or "upload",
                media_type=mediaType,
                note=note,
                restrict_to_in_progress=not _is_staff(caller),
            )
        )
    except (InvalidTransition, ValueError) as exc:
        _handle_domain_errors(exc)
    except LookupError as exc:
        raise _not_found("entry", entry_id) from exc
    await session.commit()
    return AttachmentResponse(
        fileReference=attachment.file_reference,
        fileName=attachment.file_name,
        mediaType=attachment.media_type,
        uploadedAt=attachment.uploaded_at,
        note=attachment.note,
    )


@projects_router.get(
    "/{project_id}/occurrence-entries/{entry_id}/attachments/{file_reference:path}",
)
async def download_occurrence_entry_attachment(
    project_id: str,
    entry_id: str,
    file_reference: str,
    caller: CallerPermission,
    project_repo: ProjectRepo,
    proposal_repo: ProposalRepo,
    occurrence_log_repo: OccurrenceLogRepo,
    file_storage: FileStorage,
) -> Response:
    await _assert_existing_project_access(
        project_id, caller, project_repo, proposal_repo
    )
    entry = await occurrence_log_repo.get_entry_by_id(
        ObjectOccurrenceEntryId(entry_id)
    )
    if entry is None:
        raise _not_found("entry", entry_id)
    occurrence_log = await occurrence_log_repo.get_by_id(
        entry.object_occurrence_log_id
    )
    if occurrence_log is None or occurrence_log.collection_use_project_id != (
        CollectionUseProjectId(project_id)
    ):
        raise _not_found("entry", entry_id)
    return await _download_attachment(entry.attachments, file_reference, file_storage)


# ── Publication log entries ────────────────────────────────────────────────--


@projects_router.post(
    "/{project_id}/publication-entries",
    status_code=status.HTTP_201_CREATED,
    response_model=PublicationLogEntryResponse,
)
async def add_publication_entry(
    project_id: str,
    body: AddPublicationEntryRequest,
    caller: CallerPermission,
    project_repo: ProjectRepo,
    proposal_repo: ProposalRepo,
    publication_log_repo: PublicationLogRepo,
    session: DBSession,
) -> PublicationLogEntryResponse:
    await _assert_existing_project_access(
        project_id, caller, project_repo, proposal_repo
    )
    try:
        entry = await AddPublicationLogEntry(
            project_repo, publication_log_repo, proposal_repo
        ).execute(
            AddPublicationLogEntryInput(
                project_id=CollectionUseProjectId(project_id),
                caller=caller,
                note=body.note,
            )
        )
    except Exception as exc:
        _handle_domain_errors(exc)
    await session.commit()
    return await _build_publication_entry(entry, session)


@projects_router.patch(
    "/{project_id}/publication-entries/{entry_id}",
    response_model=PublicationLogEntryResponse,
)
async def edit_publication_entry(
    project_id: str,
    entry_id: str,
    body: EditPublicationEntryRequest,
    caller: CallerPermission,
    project_repo: ProjectRepo,
    proposal_repo: ProposalRepo,
    publication_log_repo: PublicationLogRepo,
    session: DBSession,
) -> PublicationLogEntryResponse:
    await _assert_existing_project_access(
        project_id, caller, project_repo, proposal_repo
    )
    try:
        entry = await EditPublicationLogEntry(
            project_repo, publication_log_repo
        ).execute(
            EditPublicationLogEntryInput(
                project_id=CollectionUseProjectId(project_id),
                entry_id=PublicationLogEntryId(entry_id),
                caller=caller,
                note=body.note,
            )
        )
    except LookupError as exc:
        raise _not_found("entry", entry_id) from exc
    except Exception as exc:
        _handle_domain_errors(exc)
    await session.commit()
    return await _build_publication_entry(entry, session)


@projects_router.get(
    "/{project_id}/publication-entries",
    response_model=PaginatedPublicationEntriesResponse,
)
async def list_publication_entries(
    project_id: str,
    caller: CallerPermission,
    project_repo: ProjectRepo,
    proposal_repo: ProposalRepo,
    publication_log_repo: PublicationLogRepo,
    session: DBSession,
    added_by: Annotated[str | None, Query()] = None,
    page: Annotated[int, Query(ge=0)] = 0,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PaginatedPublicationEntriesResponse:
    await _assert_existing_project_access(
        project_id, caller, project_repo, proposal_repo
    )
    publication_log = await publication_log_repo.get_by_project_id(
        CollectionUseProjectId(project_id)
    )
    entries, total = await publication_log_repo.list_entries_by_project(
        CollectionUseProjectId(project_id), added_by, page, size
    )
    items = [await _build_publication_entry(e, session) for e in entries]
    return PaginatedPublicationEntriesResponse(
        projectId=project_id,
        publicationLog=(
            await _build_publication_log_response(publication_log, session)
            if publication_log
            else None
        ),
        content=items,
        page=page,
        size=size,
        totalElements=total,
        totalPages=math.ceil(total / size) if size > 0 else 0,
    )


@projects_router.get(
    "/{project_id}/publication-log",
    response_model=PublicationLogResponse,
)
async def get_publication_log(
    project_id: str,
    caller: CallerPermission,
    project_repo: ProjectRepo,
    proposal_repo: ProposalRepo,
    publication_log_repo: PublicationLogRepo,
    session: DBSession,
) -> PublicationLogResponse:
    await _assert_existing_project_access(
        project_id, caller, project_repo, proposal_repo
    )
    publication_log = await GetPublicationLog(
        project_repo, publication_log_repo
    ).execute(GetPublicationLogInput(project_id=CollectionUseProjectId(project_id)))
    if publication_log is None:
        raise _not_found("publication_log", project_id)
    return await _build_publication_log_response(publication_log, session)


@projects_router.post(
    "/{project_id}/publication-entries/{entry_id}/attachments",
    status_code=status.HTTP_201_CREATED,
    response_model=AttachmentResponse,
)
async def add_publication_entry_attachment(
    project_id: str,
    entry_id: str,
    caller: CallerPermission,
    project_repo: ProjectRepo,
    proposal_repo: ProposalRepo,
    publication_log_repo: PublicationLogRepo,
    file_storage: FileStorage,
    session: DBSession,
    file: Annotated[UploadFile, File(...)],
    mediaType: Annotated[str, Form(...)],
    note: Annotated[str | None, Form()] = None,
) -> AttachmentResponse:
    await _assert_existing_project_access(
        project_id, caller, project_repo, proposal_repo
    )
    content = await read_upload_capped(file)
    try:
        attachment = await AddPublicationEntryAttachment(
            project_repo, publication_log_repo, file_storage
        ).execute(
            AddPublicationEntryAttachmentInput(
                project_id=CollectionUseProjectId(project_id),
                entry_id=PublicationLogEntryId(entry_id),
                caller=caller,
                file_content=content,
                file_name=file.filename or "upload",
                media_type=mediaType,
                note=note,
            )
        )
    except LookupError as exc:
        raise _not_found("entry", entry_id) from exc
    except Exception as exc:
        _handle_domain_errors(exc)
    await session.commit()
    return AttachmentResponse(
        fileReference=attachment.file_reference,
        fileName=attachment.file_name,
        mediaType=attachment.media_type,
        uploadedAt=attachment.uploaded_at,
        note=attachment.note,
    )


@projects_router.get(
    "/{project_id}/publication-entries/{entry_id}/attachments/{file_reference:path}",
)
async def download_publication_entry_attachment(
    project_id: str,
    entry_id: str,
    file_reference: str,
    caller: CallerPermission,
    project_repo: ProjectRepo,
    proposal_repo: ProposalRepo,
    publication_log_repo: PublicationLogRepo,
    file_storage: FileStorage,
) -> Response:
    await _assert_existing_project_access(
        project_id, caller, project_repo, proposal_repo
    )
    entry = await publication_log_repo.get_entry_by_id(
        PublicationLogEntryId(entry_id)
    )
    if entry is None:
        raise _not_found("entry", entry_id)
    publication_log = await publication_log_repo.get_by_id(entry.publication_log_id)
    if publication_log is None or publication_log.collection_use_project_id != (
        CollectionUseProjectId(project_id)
    ):
        raise _not_found("entry", entry_id)
    return await _download_attachment(entry.attachments, file_reference, file_storage)


