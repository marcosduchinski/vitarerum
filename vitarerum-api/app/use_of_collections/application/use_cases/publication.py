"""Publication log use cases.

Each project has at most one PublicationLog, lazily created on first entry. Write
access is phase/role gated: while the project is IN_PROGRESS only the external
requester may write; once COMPLETED only curatorial/collections/direction staff
may write; no other status allows writes.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.identity.public import Actor, GroupName
from app.shared.authorization import is_in_group, is_staff
from app.shared.exceptions import AccessDenied
from app.use_of_collections.application.ports import (
    CollectionUseProjectRepository,
    FileStoragePort,
    ProposalRepository,
    PublicationLogRepository,
)
from app.use_of_collections.application.use_cases._shared import (
    _new_id,
    _new_publication_log_reference_number,
    _now,
    _store_attachment,
)
from app.use_of_collections.domain.enums import UseStatus
from app.use_of_collections.domain.models import (
    Attachment,
    CollectionUseProject,
    CollectionUseProjectId,
    InvalidTransition,
    PermissionId,
    PublicationLog,
    PublicationLogEntry,
    PublicationLogEntryId,
    PublicationLogId,
    ReferenceNumber,
)

_PUBLICATION_STAFF_GROUPS = (
    GroupName.CURATORIAL,
    GroupName.COLLECTIONS_MANAGEMENT,
    GroupName.DIRECTION,
)


def _check_publication_entry_allowed(
    project: CollectionUseProject, caller: Actor
) -> None:
    """Phase/role rule for publication writes: while the project is IN_PROGRESS
    only the external requester may write; once COMPLETED only curatorial,
    collections-management or direction staff may write; no other status allows
    writes at all."""
    if project.status == UseStatus.IN_PROGRESS:
        if is_staff(caller):
            raise AccessDenied(
                "While the project is IN_PROGRESS only the requester can "
                "add publication entries"
            )
    elif project.status == UseStatus.COMPLETED:
        if not is_in_group(caller, _PUBLICATION_STAFF_GROUPS):
            raise AccessDenied(
                "Once the project is COMPLETED only curatorial, "
                "collections-management or direction staff can add "
                "publication entries"
            )
    else:
        raise InvalidTransition(
            "Publication entries can only be added while the project is "
            "IN_PROGRESS or COMPLETED"
        )


async def _get_or_create_publication_log(
    project_id: CollectionUseProjectId,
    repository: PublicationLogRepository,
    curator: PermissionId | None,
) -> PublicationLog:
    publication_log = await repository.get_by_project_id(project_id)
    if publication_log is None:
        publication_log = PublicationLog(
            id=PublicationLogId(_new_id()),
            reference_number=ReferenceNumber(_new_publication_log_reference_number()),
            collection_use_project_id=project_id,
            curator=curator,
        )
        await repository.add(publication_log)
    return publication_log


@dataclass(slots=True)
class AddPublicationLogEntryInput:
    project_id: CollectionUseProjectId
    caller: Actor
    note: str


class AddPublicationLogEntry:
    def __init__(
        self,
        project_repository: CollectionUseProjectRepository,
        publication_log_repository: PublicationLogRepository,
        proposal_repository: ProposalRepository,
    ) -> None:
        self._project_repo = project_repository
        self._repo = publication_log_repository
        self._proposal_repo = proposal_repository

    async def execute(self, data: AddPublicationLogEntryInput) -> PublicationLogEntry:
        project = await self._project_repo.get_by_id(data.project_id)
        if project is None:
            raise LookupError(f"No project found with id {data.project_id}")
        _check_publication_entry_allowed(project, data.caller)
        # The curator is informational: the staff member related to the project,
        # taken from the proposal's assignee when the log is first created.
        proposal = await self._proposal_repo.get_by_project_id(data.project_id)
        curator = proposal.assigned_to if proposal is not None else None
        publication_log = await _get_or_create_publication_log(
            data.project_id, self._repo, curator
        )
        entry = PublicationLogEntry(
            id=PublicationLogEntryId(_new_id()),
            publication_log_id=publication_log.id,
            added_at=_now(),
            added_by=data.caller.id,
            note=data.note,
        )
        publication_log.add_entry(entry)
        await self._repo.save_entry(entry)
        return entry


@dataclass(slots=True)
class EditPublicationLogEntryInput:
    project_id: CollectionUseProjectId
    entry_id: PublicationLogEntryId
    caller: Actor
    note: str


class EditPublicationLogEntry:
    def __init__(
        self,
        project_repository: CollectionUseProjectRepository,
        publication_log_repository: PublicationLogRepository,
    ) -> None:
        self._project_repo = project_repository
        self._repo = publication_log_repository

    async def execute(self, data: EditPublicationLogEntryInput) -> PublicationLogEntry:
        project = await self._project_repo.get_by_id(data.project_id)
        if project is None:
            raise LookupError(f"No project found with id {data.project_id}")
        _check_publication_entry_allowed(project, data.caller)
        entry = await self._repo.get_entry_by_id(data.entry_id)
        if entry is None:
            raise LookupError(f"No entry found with id {data.entry_id}")
        publication_log = await self._repo.get_by_id(entry.publication_log_id)
        if (
            publication_log is None
            or publication_log.collection_use_project_id != data.project_id
        ):
            raise LookupError(f"No entry found with id {data.entry_id}")
        entry.edit(note=data.note)
        await self._repo.save_entry(entry)
        return entry


@dataclass(slots=True)
class GetPublicationLogInput:
    project_id: CollectionUseProjectId


class GetPublicationLog:
    def __init__(
        self,
        project_repository: CollectionUseProjectRepository,
        publication_log_repository: PublicationLogRepository,
    ) -> None:
        self._project_repo = project_repository
        self._repo = publication_log_repository

    async def execute(self, data: GetPublicationLogInput) -> PublicationLog | None:
        project = await self._project_repo.get_by_id(data.project_id)
        if project is None:
            raise LookupError(f"No project found with id {data.project_id}")
        return await self._repo.get_by_project_id(data.project_id)


@dataclass(slots=True)
class AddPublicationEntryAttachmentInput:
    project_id: CollectionUseProjectId
    entry_id: PublicationLogEntryId
    caller: Actor
    file_content: bytes
    file_name: str
    media_type: str
    note: str | None = None


class AddPublicationEntryAttachment:
    def __init__(
        self,
        project_repository: CollectionUseProjectRepository,
        publication_log_repository: PublicationLogRepository,
        file_storage: FileStoragePort,
    ) -> None:
        self._project_repo = project_repository
        self._repo = publication_log_repository
        self._storage = file_storage

    async def execute(self, data: AddPublicationEntryAttachmentInput) -> Attachment:
        project = await self._project_repo.get_by_id(data.project_id)
        if project is None:
            raise LookupError(f"No project found with id {data.project_id}")
        _check_publication_entry_allowed(project, data.caller)
        entry = await self._repo.get_entry_by_id(data.entry_id)
        if entry is None:
            raise LookupError(f"No entry found with id {data.entry_id}")
        publication_log = await self._repo.get_by_id(entry.publication_log_id)
        if (
            publication_log is None
            or publication_log.collection_use_project_id != data.project_id
        ):
            raise LookupError(f"No entry found with id {data.entry_id}")
        attachment = await _store_attachment(
            self._storage,
            "publication-entries",
            str(data.entry_id),
            data.file_content,
            data.file_name,
            data.media_type,
            data.note,
        )
        entry.add_attachment(attachment)
        try:
            await self._repo.save_entry(entry)
        except BaseException:
            # Don't leave an orphaned file when the entry fails to persist.
            await self._storage.delete(attachment.file_reference)
            raise
        return attachment
