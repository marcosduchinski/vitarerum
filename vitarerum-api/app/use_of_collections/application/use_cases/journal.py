"""Object journal use cases: the access log and the occurrence log.

Each project has at most one ObjectAccessLog and one ObjectOccurrenceLog, lazily
created on first entry. Every entry links to a CollectionUseObject of the project
(validated here against the project's own objects) — the CollectionUseObject is
the carrier of the object's inventory snapshot, so journaling never reads back
into the proposal.

The access-log and occurrence-log use cases share the same shape; the common
preamble (load a writable project), entry-log validation, and attachment
storage are factored into the helpers at the top of this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.identity.public import Actor
from app.use_of_collections.application.ports import (
    CollectionUseProjectRepository,
    FileStoragePort,
    ObjectAccessLogRepository,
    ObjectOccurrenceLogRepository,
)
from app.use_of_collections.application.use_cases._shared import (
    _new_access_log_reference_number,
    _new_id,
    _new_occurrence_log_reference_number,
    _now,
    _store_attachment,
    _validate_collection_use_object,
)
from app.use_of_collections.domain.enums import UseStatus
from app.use_of_collections.domain.models import (
    Attachment,
    CollectionUseObjectId,
    CollectionUseProject,
    CollectionUseProjectId,
    InvalidTransition,
    ObjectAccessLog,
    ObjectAccessLogId,
    ObjectLogEntry,
    ObjectLogEntryId,
    ObjectOccurrenceEntry,
    ObjectOccurrenceEntryId,
    ObjectOccurrenceLog,
    ObjectOccurrenceLogId,
    ReferenceNumber,
)

# ── Shared helpers ─────────────────────────────────────────────────────────────


class _ConcludableLog(Protocol):
    """Structural view shared by ObjectAccessLog and ObjectOccurrenceLog: the
    two attributes the entry-log validation needs."""

    collection_use_project_id: CollectionUseProjectId

    @property
    def is_concluded(self) -> bool: ...


def _check_entry_allowed(
    project: CollectionUseProject, restrict_to_in_progress: bool
) -> None:
    if restrict_to_in_progress and project.status != UseStatus.IN_PROGRESS:
        raise InvalidTransition(
            "Entries can only be added while the project is IN_PROGRESS"
        )


async def _load_writable_project(
    project_repository: CollectionUseProjectRepository,
    project_id: CollectionUseProjectId,
    restrict_to_in_progress: bool,
) -> CollectionUseProject:
    """Load the project an entry belongs to, enforcing the IN_PROGRESS gate."""
    project = await project_repository.get_by_id(project_id)
    if project is None:
        raise LookupError(f"No project found with id {project_id}")
    _check_entry_allowed(project, restrict_to_in_progress)
    return project


def _assert_entry_log_writable(
    log: _ConcludableLog | None,
    project_id: CollectionUseProjectId,
    entry_id: str,
    *,
    action: str,
    log_kind: str,
) -> None:
    """Confirm the entry's parent log belongs to this project and is not
    concluded. A missing/foreign log is reported as a missing entry (the entry
    id is the caller's only handle); a concluded log blocks the write."""
    if log is None or log.collection_use_project_id != project_id:
        raise LookupError(f"No entry found with id {entry_id}")
    if log.is_concluded:
        raise InvalidTransition(f"Cannot {action} a concluded {log_kind}")


# ── Object access log ──────────────────────────────────────────────────────────


async def _get_or_create_access_log(
    project_id: CollectionUseProjectId,
    repository: ObjectAccessLogRepository,
) -> ObjectAccessLog:
    access_log = await repository.get_by_project_id(project_id)
    if access_log is None:
        access_log = ObjectAccessLog(
            id=ObjectAccessLogId(_new_id()),
            reference_number=ReferenceNumber(_new_access_log_reference_number()),
            collection_use_project_id=project_id,
        )
        await repository.add(access_log)
    return access_log


@dataclass(slots=True)
class AddObjectLogEntryInput:
    project_id: CollectionUseProjectId
    caller: Actor
    collection_use_object_id: CollectionUseObjectId
    number_of_objects: int
    observations: str | None = None
    restrict_to_in_progress: bool = False


class AddObjectLogEntry:
    def __init__(
        self,
        project_repository: CollectionUseProjectRepository,
        access_log_repository: ObjectAccessLogRepository,
    ) -> None:
        self._project_repo = project_repository
        self._repo = access_log_repository

    async def execute(self, data: AddObjectLogEntryInput) -> ObjectLogEntry:
        project = await _load_writable_project(
            self._project_repo, data.project_id, data.restrict_to_in_progress
        )
        _validate_collection_use_object(project, data.collection_use_object_id)
        access_log = await _get_or_create_access_log(data.project_id, self._repo)
        entry = ObjectLogEntry(
            id=ObjectLogEntryId(_new_id()),
            object_access_log_id=access_log.id,
            collection_use_object_id=data.collection_use_object_id,
            number_of_objects=data.number_of_objects,
            added_at=_now(),
            added_by=data.caller.id,
            observations=data.observations,
        )
        access_log.add_object_log_entry(entry)
        await self._repo.save_entry(entry)
        return entry


@dataclass(slots=True)
class EditObjectLogEntryInput:
    project_id: CollectionUseProjectId
    entry_id: ObjectLogEntryId
    caller: Actor
    added_at: datetime | None = None
    number_of_objects: int | None = None
    observations: str | None = None
    update_observations: bool = False
    restrict_to_in_progress: bool = False


class EditObjectLogEntry:
    def __init__(
        self,
        project_repository: CollectionUseProjectRepository,
        access_log_repository: ObjectAccessLogRepository,
    ) -> None:
        self._project_repo = project_repository
        self._repo = access_log_repository

    async def execute(self, data: EditObjectLogEntryInput) -> ObjectLogEntry:
        await _load_writable_project(
            self._project_repo, data.project_id, data.restrict_to_in_progress
        )
        entry = await self._repo.get_entry_by_id(data.entry_id)
        if entry is None:
            raise LookupError(f"No entry found with id {data.entry_id}")
        access_log = await self._repo.get_by_id(entry.object_access_log_id)
        _assert_entry_log_writable(
            access_log,
            data.project_id,
            data.entry_id,
            action="edit entries of",
            log_kind="object access log",
        )
        entry.edit(
            added_at=data.added_at if data.added_at is not None else entry.added_at,
            number_of_objects=(
                data.number_of_objects
                if data.number_of_objects is not None
                else entry.number_of_objects
            ),
            observations=(
                data.observations if data.update_observations else entry.observations
            ),
        )
        await self._repo.save_entry(entry)
        return entry


@dataclass(slots=True)
class GetObjectAccessLogInput:
    project_id: CollectionUseProjectId


class GetObjectAccessLog:
    def __init__(
        self,
        project_repository: CollectionUseProjectRepository,
        access_log_repository: ObjectAccessLogRepository,
    ) -> None:
        self._project_repo = project_repository
        self._repo = access_log_repository

    async def execute(self, data: GetObjectAccessLogInput) -> ObjectAccessLog | None:
        project = await self._project_repo.get_by_id(data.project_id)
        if project is None:
            raise LookupError(f"No project found with id {data.project_id}")
        return await self._repo.get_by_project_id(data.project_id)


@dataclass(slots=True)
class AddLogEntryAttachmentInput:
    project_id: CollectionUseProjectId
    entry_id: ObjectLogEntryId
    caller: Actor
    file_content: bytes
    file_name: str
    media_type: str
    note: str | None = None
    restrict_to_in_progress: bool = False


class AddLogEntryAttachment:
    def __init__(
        self,
        project_repository: CollectionUseProjectRepository,
        access_log_repository: ObjectAccessLogRepository,
        file_storage: FileStoragePort,
    ) -> None:
        self._project_repo = project_repository
        self._repo = access_log_repository
        self._storage = file_storage

    async def execute(self, data: AddLogEntryAttachmentInput) -> Attachment:
        await _load_writable_project(
            self._project_repo, data.project_id, data.restrict_to_in_progress
        )
        entry = await self._repo.get_entry_by_id(data.entry_id)
        if entry is None:
            raise LookupError(f"No entry found with id {data.entry_id}")
        access_log = await self._repo.get_by_id(entry.object_access_log_id)
        _assert_entry_log_writable(
            access_log,
            data.project_id,
            data.entry_id,
            action="add attachments to",
            log_kind="object access log",
        )
        attachment = await _store_attachment(
            self._storage,
            "log-entries",
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


@dataclass(slots=True)
class RemoveLogEntryAttachmentInput:
    project_id: CollectionUseProjectId
    entry_id: ObjectLogEntryId
    caller: Actor
    file_reference: str
    restrict_to_in_progress: bool = False


class RemoveLogEntryAttachment:
    def __init__(
        self,
        project_repository: CollectionUseProjectRepository,
        access_log_repository: ObjectAccessLogRepository,
    ) -> None:
        self._project_repo = project_repository
        self._repo = access_log_repository

    async def execute(self, data: RemoveLogEntryAttachmentInput) -> Attachment:
        await _load_writable_project(
            self._project_repo, data.project_id, data.restrict_to_in_progress
        )
        entry = await self._repo.get_entry_by_id(data.entry_id)
        if entry is None:
            raise LookupError(f"No entry found with id {data.entry_id}")
        access_log = await self._repo.get_by_id(entry.object_access_log_id)
        _assert_entry_log_writable(
            access_log,
            data.project_id,
            data.entry_id,
            action="remove attachments from",
            log_kind="object access log",
        )
        attachment = entry.remove_attachment(data.file_reference)
        await self._repo.save_entry(entry)
        return attachment


# ── Object occurrence log ──────────────────────────────────────────────────────


async def _get_or_create_occurrence_log(
    project_id: CollectionUseProjectId,
    repository: ObjectOccurrenceLogRepository,
) -> ObjectOccurrenceLog:
    occurrence_log = await repository.get_by_project_id(project_id)
    if occurrence_log is None:
        occurrence_log = ObjectOccurrenceLog(
            id=ObjectOccurrenceLogId(_new_id()),
            reference_number=ReferenceNumber(_new_occurrence_log_reference_number()),
            collection_use_project_id=project_id,
        )
        await repository.add(occurrence_log)
    return occurrence_log


@dataclass(slots=True)
class AddObjectOccurrenceEntryInput:
    project_id: CollectionUseProjectId
    caller: Actor
    collection_use_object_id: CollectionUseObjectId
    number_of_objects: int
    occurrence_date: datetime
    location: str
    detailed_description: str
    testimonial: str | None = None
    restrict_to_in_progress: bool = False


class AddObjectOccurrenceEntry:
    def __init__(
        self,
        project_repository: CollectionUseProjectRepository,
        occurrence_log_repository: ObjectOccurrenceLogRepository,
    ) -> None:
        self._project_repo = project_repository
        self._repo = occurrence_log_repository

    async def execute(
        self, data: AddObjectOccurrenceEntryInput
    ) -> ObjectOccurrenceEntry:
        project = await _load_writable_project(
            self._project_repo, data.project_id, data.restrict_to_in_progress
        )
        _validate_collection_use_object(project, data.collection_use_object_id)
        occurrence_log = await _get_or_create_occurrence_log(
            data.project_id, self._repo
        )
        entry = ObjectOccurrenceEntry(
            id=ObjectOccurrenceEntryId(_new_id()),
            object_occurrence_log_id=occurrence_log.id,
            collection_use_object_id=data.collection_use_object_id,
            number_of_objects=data.number_of_objects,
            occurrence_date=data.occurrence_date,
            location=data.location,
            reported_by=data.caller.id,
            detailed_description=data.detailed_description,
            testimonial=data.testimonial,
        )
        occurrence_log.add_object_occurrence_entry(entry)
        await self._repo.save_entry(entry)
        return entry


@dataclass(slots=True)
class EditObjectOccurrenceEntryInput:
    project_id: CollectionUseProjectId
    entry_id: ObjectOccurrenceEntryId
    caller: Actor
    number_of_objects: int | None = None
    occurrence_date: datetime | None = None
    location: str | None = None
    detailed_description: str | None = None
    testimonial: str | None = None
    update_testimonial: bool = False
    restrict_to_in_progress: bool = False


class EditObjectOccurrenceEntry:
    def __init__(
        self,
        project_repository: CollectionUseProjectRepository,
        occurrence_log_repository: ObjectOccurrenceLogRepository,
    ) -> None:
        self._project_repo = project_repository
        self._repo = occurrence_log_repository

    async def execute(
        self, data: EditObjectOccurrenceEntryInput
    ) -> ObjectOccurrenceEntry:
        await _load_writable_project(
            self._project_repo, data.project_id, data.restrict_to_in_progress
        )
        entry = await self._repo.get_entry_by_id(data.entry_id)
        if entry is None:
            raise LookupError(f"No entry found with id {data.entry_id}")
        occurrence_log = await self._repo.get_by_id(entry.object_occurrence_log_id)
        _assert_entry_log_writable(
            occurrence_log,
            data.project_id,
            data.entry_id,
            action="edit entries of",
            log_kind="object occurrence log",
        )
        entry.edit(
            number_of_objects=(
                data.number_of_objects
                if data.number_of_objects is not None
                else entry.number_of_objects
            ),
            occurrence_date=(
                data.occurrence_date
                if data.occurrence_date is not None
                else entry.occurrence_date
            ),
            location=data.location if data.location is not None else entry.location,
            detailed_description=(
                data.detailed_description
                if data.detailed_description is not None
                else entry.detailed_description
            ),
            testimonial=(
                data.testimonial if data.update_testimonial else entry.testimonial
            ),
        )
        await self._repo.save_entry(entry)
        return entry


@dataclass(slots=True)
class GetObjectOccurrenceLogInput:
    project_id: CollectionUseProjectId


class GetObjectOccurrenceLog:
    def __init__(
        self,
        project_repository: CollectionUseProjectRepository,
        occurrence_log_repository: ObjectOccurrenceLogRepository,
    ) -> None:
        self._project_repo = project_repository
        self._repo = occurrence_log_repository

    async def execute(
        self, data: GetObjectOccurrenceLogInput
    ) -> ObjectOccurrenceLog | None:
        project = await self._project_repo.get_by_id(data.project_id)
        if project is None:
            raise LookupError(f"No project found with id {data.project_id}")
        return await self._repo.get_by_project_id(data.project_id)


@dataclass(slots=True)
class AddOccurrenceEntryAttachmentInput:
    project_id: CollectionUseProjectId
    entry_id: ObjectOccurrenceEntryId
    caller: Actor
    file_content: bytes
    file_name: str
    media_type: str
    note: str | None = None
    restrict_to_in_progress: bool = False


class AddOccurrenceEntryAttachment:
    def __init__(
        self,
        project_repository: CollectionUseProjectRepository,
        occurrence_log_repository: ObjectOccurrenceLogRepository,
        file_storage: FileStoragePort,
    ) -> None:
        self._project_repo = project_repository
        self._repo = occurrence_log_repository
        self._storage = file_storage

    async def execute(self, data: AddOccurrenceEntryAttachmentInput) -> Attachment:
        await _load_writable_project(
            self._project_repo, data.project_id, data.restrict_to_in_progress
        )
        entry = await self._repo.get_entry_by_id(data.entry_id)
        if entry is None:
            raise LookupError(f"No entry found with id {data.entry_id}")
        occurrence_log = await self._repo.get_by_id(entry.object_occurrence_log_id)
        _assert_entry_log_writable(
            occurrence_log,
            data.project_id,
            data.entry_id,
            action="add attachments to",
            log_kind="object occurrence log",
        )
        attachment = await _store_attachment(
            self._storage,
            "occurrence-entries",
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


@dataclass(slots=True)
class RemoveOccurrenceEntryAttachmentInput:
    project_id: CollectionUseProjectId
    entry_id: ObjectOccurrenceEntryId
    caller: Actor
    file_reference: str
    restrict_to_in_progress: bool = False


class RemoveOccurrenceEntryAttachment:
    def __init__(
        self,
        project_repository: CollectionUseProjectRepository,
        occurrence_log_repository: ObjectOccurrenceLogRepository,
    ) -> None:
        self._project_repo = project_repository
        self._repo = occurrence_log_repository

    async def execute(self, data: RemoveOccurrenceEntryAttachmentInput) -> Attachment:
        await _load_writable_project(
            self._project_repo, data.project_id, data.restrict_to_in_progress
        )
        entry = await self._repo.get_entry_by_id(data.entry_id)
        if entry is None:
            raise LookupError(f"No entry found with id {data.entry_id}")
        occurrence_log = await self._repo.get_by_id(entry.object_occurrence_log_id)
        _assert_entry_log_writable(
            occurrence_log,
            data.project_id,
            data.entry_id,
            action="remove attachments from",
            log_kind="object occurrence log",
        )
        attachment = entry.remove_attachment(data.file_reference)
        await self._repo.save_entry(entry)
        return attachment
