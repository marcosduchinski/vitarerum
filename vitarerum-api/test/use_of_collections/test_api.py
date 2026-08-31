import base64
import io
import zipfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from docx import Document as DocxDocument
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.database import get_async_session
from app.identity.infrastructure.models import (
    GroupRecord,
    PermissionRecord,
    UserRecord,
)
from app.identity.public import Actor, GroupName, PermissionId, PermissionView, UserView
from app.main import app
from app.reference_numbers.public import ReferenceKind
from app.shared.dependencies import get_caller_permission
from app.shared.file_storage import build_file_storage
from app.use_of_collections.application.ports import (
    ProjectFilters,
    ProposalFilters,
    ResolvedExternalRequester,
)
from app.use_of_collections.domain.enums import (
    MediaType,
    ProposalEventType,
    ProposalStatus,
    SubmissionChannel,
    UseStatus,
    UseType,
)
from app.use_of_collections.domain.models import (
    Attachment,
    CollectionUseObject,
    CollectionUseObjectId,
    CollectionUseProject,
    CollectionUseProjectId,
    Conversation,
    ConversationId,
    Document,
    DocumentId,
    DocumentType,
    EmailAddress,
    Message,
    MessageId,
    ObjectAccessLog,
    ObjectAccessLogId,
    ObjectLogEntry,
    ObjectLogEntryId,
    ObjectOccurrenceEntry,
    ObjectOccurrenceEntryId,
    ObjectOccurrenceLog,
    ObjectOccurrenceLogId,
    Proposal,
    ProposalEvent,
    ProposalId,
    PublicationLog,
    PublicationLogEntry,
    PublicationLogEntryId,
    PublicationLogId,
    ReferenceNumber,
    RequestedObject,
    RequestedObjectId,
    RequesterContact,
)
from app.use_of_collections.infrastructure.docx_rendering import DOCX_MEDIA_TYPE
from app.use_of_collections.presentation.dependencies import (
    get_access_log_repo,
    get_conversation_repo,
    get_external_requester_provisioner,
    get_file_storage,
    get_notifications_dispatcher,
    get_occurrence_log_repo,
    get_project_repo,
    get_proposal_notification_email_sender,
    get_proposal_repo,
    get_publication_log_repo,
    get_reader,
    get_reference_number_generator,
    get_requester_access_email_sender,
)


def _docx_bytes() -> bytes:
    """Minimal valid DOCX: a ZIP carrying the OOXML content-types part."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", "<w:document/>")
    return buf.getvalue()


_CALLER = Actor(
    id=PermissionId("permission-1"),
    group=GroupName.EXTERNAL,
    email="alice@example.org",
)

_STAFF_CALLER = Actor(
    id=PermissionId("permission-staff"),
    group=GroupName.CURATORIAL,
    email="staff@example.org",
)


def _permission_record(
    permission_id: str,
    group_name: GroupName,
    *,
    user_id: str | None = None,
    user_name: str | None = None,
    user_email: str | None = None,
) -> PermissionRecord:
    user_id = user_id or f"user-{permission_id}"
    group_id = f"group-{group_name.value}"
    record = PermissionRecord(id=permission_id, user_id=user_id, group_id=group_id)
    record.user = UserRecord(
        id=user_id,
        name=user_name or f"User {permission_id}",
        email=user_email or f"{permission_id}@example.org",
        password_hash="",
    )
    record.group = GroupRecord(id=group_id, name=group_name)
    return record


def _proposal(
    proposal_id: str = "prop-1",
    requested_by: PermissionId | None = None,
    status: ProposalStatus = ProposalStatus.PENDING,
    documents: list[Document] | None = None,
) -> Proposal:
    requested_by = requested_by or PermissionId("permission-1")
    return Proposal(
        id=ProposalId(proposal_id),
        reference_number=ReferenceNumber("VRP-20260601-0001"),
        title="Proposal title",
        collection_use_project_id=CollectionUseProjectId("proj-1"),
        intended_use=UseType.IN_SITU_VISIT,
        begin_date=date(2026, 6, 1),
        end_date=date(2026, 6, 7),
        status=status,
        requested_by=requested_by,
        submitted_at=datetime(2026, 6, 7, tzinfo=UTC),
        submission_channel=SubmissionChannel.AUTHENTICATED,
        documents=documents or [],
    )


def _collection_use_object(
    object_id: str = "cuo-1", inventory_number: str = "INV-001"
) -> CollectionUseObject:
    return CollectionUseObject(
        id=CollectionUseObjectId(object_id),
        inventory_number=inventory_number,
        category="fox head",
        description="a fox head",
        requested_at=datetime(2026, 6, 1, tzinfo=UTC),
        requested_by=PermissionId("permission-1"),
    )


def _project(
    project_id: str = "proj-1",
    requested_by: PermissionId | None = None,
    status: UseStatus = UseStatus.CREATED,
    objects: list[CollectionUseObject] | None = None,
) -> CollectionUseProject:
    requested_by = requested_by or PermissionId("permission-1")
    return CollectionUseProject(
        id=CollectionUseProjectId(project_id),
        reference_number=ReferenceNumber("CUP-ABCDEFG1"),
        title="Project title",
        purpose="Use collection",
        intended_use=UseType.IN_SITU_VISIT,
        status=status,
        begin_date=date(2026, 6, 1),
        end_date=date(2026, 6, 7),
        requested_by=requested_by,
        proposal_id=ProposalId("prop-1"),
        objects=objects if objects is not None else [],
    )


class InMemoryProjectRepository:
    def __init__(self) -> None:
        self.items: dict[str, CollectionUseProject] = {}

    async def add(self, project: CollectionUseProject) -> None:
        self.items[project.id] = project

    async def get_by_id(self, project_id: str) -> CollectionUseProject | None:
        return self.items.get(project_id)

    async def get_by_reference(
        self, ref: ReferenceNumber
    ) -> CollectionUseProject | None:
        return next((p for p in self.items.values() if p.reference_number == ref), None)

    async def save(self, project: CollectionUseProject) -> None:
        self.items[project.id] = project

    async def list(self, filters: ProjectFilters, page: int, size: int):
        items = list(self.items.values())
        if filters.status:
            items = [item for item in items if item.status == filters.status]
        if filters.use_type:
            items = [item for item in items if item.intended_use == filters.use_type]
        if filters.requested_by:
            items = [
                item for item in items if item.requested_by == filters.requested_by
            ]
        if filters.origin_project_id:
            items = [
                item
                for item in items
                if item.origin_project_id == filters.origin_project_id
            ]
        if filters.date_from:
            items = [item for item in items if item.begin_date >= filters.date_from]
        if filters.date_to:
            items = [item for item in items if item.begin_date <= filters.date_to]
        if filters.search:
            pattern = filters.search.lower()
            items = [
                item
                for item in items
                if pattern in item.title.lower()
                or pattern in item.reference_number.value.lower()
            ]
        return items[page * size : page * size + size], len(items)


class InMemoryProposalRepository:
    def __init__(self) -> None:
        self.items: dict[str, Proposal] = {}
        self.project_lookup_count = 0

    async def add(self, proposal: Proposal) -> None:
        self.items[proposal.id] = proposal

    async def next_reference_number_for(self, day: date) -> ReferenceNumber:
        prefix = f"VRP-{day:%Y%m%d}-"
        latest = max(
            (
                proposal.reference_number.value
                for proposal in self.items.values()
                if proposal.reference_number.value.startswith(prefix)
            ),
            default=None,
        )
        sequence = int(latest.removeprefix(prefix)) + 1 if latest else 1
        return ReferenceNumber(f"{prefix}{sequence:04d}")

    async def get_by_id(self, proposal_id: ProposalId) -> Proposal | None:
        return self.items.get(proposal_id)

    async def get_by_project_id(
        self, project_id: CollectionUseProjectId
    ) -> Proposal | None:
        self.project_lookup_count += 1
        return next(
            (
                proposal
                for proposal in self.items.values()
                if proposal.collection_use_project_id == project_id
            ),
            None,
        )

    async def list_by_project_ids(
        self, project_ids: list[CollectionUseProjectId]
    ) -> list[Proposal]:
        self.project_lookup_count += 1
        project_id_set = set(project_ids)
        return [
            proposal
            for proposal in self.items.values()
            if proposal.collection_use_project_id in project_id_set
        ]

    async def save(self, proposal: Proposal) -> None:
        self.items[proposal.id] = proposal

    async def list(self, filters: ProposalFilters, page: int, size: int):
        if size == 10000:
            raise AssertionError("Use targeted project proposal lookup instead")
        items = list(self.items.values())
        if filters.statuses:
            items = [item for item in items if item.status in filters.statuses]
        return items[page * size : page * size + size], len(items)


class InMemoryReferenceNumberGenerator:
    def __init__(self, proposal_repo: InMemoryProposalRepository) -> None:
        self._proposal_repo = proposal_repo
        self._counters: dict[ReferenceKind, int] = {}

    async def generate(self, *, kind: ReferenceKind, on_date: date) -> ReferenceNumber:
        if kind is ReferenceKind.PROPOSAL:
            return await self._proposal_repo.next_reference_number_for(on_date)
        self._counters[kind] = self._counters.get(kind, 0) + 1
        prefixes = {
            ReferenceKind.COLLECTION_USE_PROJECT: "CUP",
            ReferenceKind.OBJECT_ACCESS_LOG: "OAL",
            ReferenceKind.OBJECT_OCCURRENCE_LOG: "OOL",
            ReferenceKind.PUBLICATION_LOG: "PUB",
        }
        return ReferenceNumber(f"{prefixes[kind]}-{self._counters[kind]:08d}")


class InMemoryConversationRepository:
    def __init__(self) -> None:
        self.items: dict[str, Conversation] = {}

    async def add(self, conversation: Conversation) -> None:
        self.items[conversation.proposal_id] = conversation

    async def get_by_proposal_id(self, proposal_id: ProposalId) -> Conversation | None:
        return self.items.get(proposal_id)

    async def save(self, conversation: Conversation) -> None:
        self.items[conversation.proposal_id] = conversation


class InMemoryAccessLogRepository:
    def __init__(self) -> None:
        self.items: dict[str, ObjectAccessLog] = {}
        self.entries: dict[str, ObjectLogEntry] = {}

    async def add(self, access_log: ObjectAccessLog) -> None:
        self.items[access_log.id] = access_log

    async def get_by_id(self, access_log_id) -> ObjectAccessLog | None:
        return self.items.get(access_log_id)

    async def get_by_project_id(self, project_id) -> ObjectAccessLog | None:
        for access_log in self.items.values():
            if access_log.collection_use_project_id == project_id:
                return access_log
        return None

    async def get_entry_by_id(self, entry_id) -> ObjectLogEntry | None:
        return self.entries.get(entry_id)

    async def save(self, access_log: ObjectAccessLog) -> None:
        self.items[access_log.id] = access_log

    async def save_entry(self, entry: ObjectLogEntry) -> None:
        self.entries[entry.id] = entry

    async def list_entries_for_object(self, project_id, collection_use_object_id):
        log_ids = {
            log.id
            for log in self.items.values()
            if log.collection_use_project_id == project_id
        }
        return [
            entry
            for entry in self.entries.values()
            if entry.object_access_log_id in log_ids
            and entry.collection_use_object_id == collection_use_object_id
        ]

    async def remove_entries(self, entry_ids):
        for entry_id in entry_ids:
            self.entries.pop(entry_id, None)

    async def list_entries_by_project(self, project_id, added_by, page, size):
        log_ids = {
            log.id
            for log in self.items.values()
            if log.collection_use_project_id == project_id
        }
        items = [
            entry
            for entry in self.entries.values()
            if entry.object_access_log_id in log_ids
            and (added_by is None or entry.added_by == added_by)
        ]
        return items[page * size : page * size + size], len(items)

    async def has_entries_for_object(self, project_id, collection_use_object_id):
        log_ids = {
            log.id
            for log in self.items.values()
            if log.collection_use_project_id == project_id
        }
        return any(
            entry.object_access_log_id in log_ids
            and entry.collection_use_object_id == collection_use_object_id
            for entry in self.entries.values()
        )


class InMemoryOccurrenceLogRepository:
    def __init__(self) -> None:
        self.items: dict[str, ObjectOccurrenceLog] = {}
        self.entries: dict[str, ObjectOccurrenceEntry] = {}

    async def add(self, occurrence_log: ObjectOccurrenceLog) -> None:
        self.items[occurrence_log.id] = occurrence_log

    async def get_by_id(self, occurrence_log_id) -> ObjectOccurrenceLog | None:
        return self.items.get(occurrence_log_id)

    async def get_by_project_id(self, project_id) -> ObjectOccurrenceLog | None:
        for occurrence_log in self.items.values():
            if occurrence_log.collection_use_project_id == project_id:
                return occurrence_log
        return None

    async def get_entry_by_id(self, entry_id) -> ObjectOccurrenceEntry | None:
        return self.entries.get(entry_id)

    async def save(self, occurrence_log: ObjectOccurrenceLog) -> None:
        self.items[occurrence_log.id] = occurrence_log

    async def save_entry(self, entry: ObjectOccurrenceEntry) -> None:
        self.entries[entry.id] = entry

    async def list_entries_for_object(self, project_id, collection_use_object_id):
        log_ids = {
            log.id
            for log in self.items.values()
            if log.collection_use_project_id == project_id
        }
        return [
            entry
            for entry in self.entries.values()
            if entry.object_occurrence_log_id in log_ids
            and entry.collection_use_object_id == collection_use_object_id
        ]

    async def remove_entries(self, entry_ids):
        for entry_id in entry_ids:
            self.entries.pop(entry_id, None)

    async def list_entries_by_project(self, project_id, reported_by, page, size):
        log_ids = {
            log.id
            for log in self.items.values()
            if log.collection_use_project_id == project_id
        }
        items = [
            entry
            for entry in self.entries.values()
            if entry.object_occurrence_log_id in log_ids
            and (reported_by is None or entry.reported_by == reported_by)
        ]
        return items[page * size : page * size + size], len(items)

    async def has_entries_for_object(self, project_id, collection_use_object_id):
        log_ids = {
            log.id
            for log in self.items.values()
            if log.collection_use_project_id == project_id
        }
        return any(
            entry.object_occurrence_log_id in log_ids
            and entry.collection_use_object_id == collection_use_object_id
            for entry in self.entries.values()
        )


class InMemoryPublicationLogRepository:
    def __init__(self) -> None:
        self.items: dict[str, PublicationLog] = {}
        self.entries: dict[str, PublicationLogEntry] = {}
        self.entries_in_use: set[str] = set()

    async def add(self, publication_log: PublicationLog) -> None:
        self.items[publication_log.id] = publication_log

    async def get_by_id(self, publication_log_id) -> PublicationLog | None:
        return self.items.get(publication_log_id)

    async def get_by_project_id(self, project_id) -> PublicationLog | None:
        for publication_log in self.items.values():
            if publication_log.collection_use_project_id == project_id:
                return publication_log
        return None

    async def get_entry_by_id(self, entry_id) -> PublicationLogEntry | None:
        return self.entries.get(entry_id)

    async def save(self, publication_log: PublicationLog) -> None:
        self.items[publication_log.id] = publication_log

    async def save_entry(self, entry: PublicationLogEntry) -> None:
        self.entries[entry.id] = entry

    async def list_entries_for_object(self, project_id, collection_use_object_id):
        log_ids = {
            log.id
            for log in self.items.values()
            if log.collection_use_project_id == project_id
        }
        return [
            entry
            for entry in self.entries.values()
            if entry.publication_log_id in log_ids
            and entry.collection_use_object_id == collection_use_object_id
        ]

    async def remove_entries(self, entry_ids):
        if any(entry_id in self.entries_in_use for entry_id in entry_ids):
            raise IntegrityError("DELETE publication_log_entries", {}, Exception())
        for entry_id in entry_ids:
            self.entries.pop(entry_id, None)

    async def list_entries_by_project(self, project_id, added_by, page, size):
        log_ids = {
            log.id
            for log in self.items.values()
            if log.collection_use_project_id == project_id
        }
        items = [
            entry
            for entry in self.entries.values()
            if entry.publication_log_id in log_ids
            and (added_by is None or entry.added_by == added_by)
        ]
        return items[page * size : page * size + size], len(items)


class InMemoryFileStorage:
    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}

    async def save(self, content: bytes, filename: str) -> str:
        self.files[filename] = content
        return filename

    async def read(self, file_reference: str) -> bytes:
        try:
            return self.files[file_reference]
        except KeyError as exc:
            raise FileNotFoundError(file_reference) from exc

    async def delete(self, file_reference: str) -> None:
        self.files.pop(file_reference, None)


class FailingSecondSaveStorage(InMemoryFileStorage):
    def __init__(self) -> None:
        super().__init__()
        self.save_calls = 0

    async def save(self, content: bytes, filename: str) -> str:
        self.save_calls += 1
        if self.save_calls == 2:
            raise RuntimeError("storage failed")
        return await super().save(content, filename)


class CommitOnlySession:
    def __init__(
        self, permission_records: dict[str, PermissionRecord] | None = None
    ) -> None:
        self._permission_records = permission_records or {}

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None

    def begin_nested(self):
        # No-op savepoint for run_with_unique_retry; the in-memory repos enforce
        # no constraints, so the operation simply runs once.
        @asynccontextmanager
        async def _noop() -> AsyncIterator[None]:
            yield

        return _noop()

    async def get(self, model, pk, **kwargs):
        if model is PermissionRecord:
            return self._permission_records.get(str(pk))
        return None

    async def execute(self, *args, **kwargs):
        class FakeResult:
            def scalar_one_or_none(self):
                return None

            def scalar_one(self):
                return 0

            def scalars(self):
                class S:
                    def all(self):
                        return []

                return S()

        return FakeResult()


class InMemoryPermissionReader:
    def __init__(self, records: dict[str, PermissionRecord]) -> None:
        self._records = records

    async def get_detail(self, permission_id: PermissionId) -> PermissionView | None:
        record = self._records.get(str(permission_id))
        return self._view(record) if record else None

    async def list_by_group(self, group: GroupName) -> list[PermissionView]:
        return [
            view
            for record in self._records.values()
            if record.group.name == group
            for view in [self._view(record)]
        ]

    def _view(self, record: PermissionRecord) -> PermissionView:
        return PermissionView(
            permission_id=record.id,
            user=UserView(
                id=record.user.id,
                name=record.user.name,
                email=record.user.email,
                password_changed_at=None,
            ),
            group=record.group.name,
        )


class RecordingRequesterProvisioner:
    """Fake ``ExternalRequesterProvisioner``. Raises if invoked with no
    ``resolved`` configured, so route tests approving an already-resolved
    proposal catch an unexpected (unnecessary) provisioning call."""

    def __init__(self, resolved: ResolvedExternalRequester | None = None) -> None:
        self._resolved = resolved
        self.calls: list[tuple[str, str]] = []

    async def provision(self, email: str, name: str) -> ResolvedExternalRequester:
        self.calls.append((email, name))
        if self._resolved is None:
            raise AssertionError("provision() should not have been called")
        return self._resolved


class RecordingAccessEmailSender:
    """Fake ``RequesterAccessEmailSender`` recording every call it receives."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str, str]] = []

    async def send_access_created(
        self,
        to_email: str,
        requester_name: str,
        login_url: str,
        temporary_password: str,
    ) -> None:
        self.calls.append((to_email, requester_name, login_url, temporary_password))


class RecordingProposalNotificationEmailSender:
    def __init__(self) -> None:
        self.submitted_calls: list[dict[str, object]] = []
        self.forwarded_calls: list[dict[str, object]] = []
        self.assigned_calls: list[dict[str, object]] = []
        self.taken_over_calls: list[dict[str, object]] = []
        self.documents_submitted_calls: list[dict[str, object]] = []
        self.corrections_submitted_calls: list[dict[str, object]] = []
        self.rejected_calls: list[dict[str, object]] = []
        self.approved_calls: list[dict[str, object]] = []
        self.project_started_calls: list[dict[str, object]] = []
        self.project_cancelled_calls: list[dict[str, object]] = []
        self.project_completed_calls: list[dict[str, object]] = []

    async def send_proposal_submitted(self, **kwargs) -> None:
        self.submitted_calls.append(kwargs)

    async def send_proposal_forwarded(self, **kwargs) -> None:
        self.forwarded_calls.append(kwargs)

    async def send_proposal_assigned(self, **kwargs) -> None:
        self.assigned_calls.append(kwargs)

    async def send_proposal_taken_over(self, **kwargs) -> None:
        self.taken_over_calls.append(kwargs)

    async def send_proposal_documents_submitted(self, **kwargs) -> None:
        self.documents_submitted_calls.append(kwargs)

    async def send_proposal_corrections_submitted(self, **kwargs) -> None:
        self.corrections_submitted_calls.append(kwargs)

    async def send_proposal_rejected(self, **kwargs) -> None:
        self.rejected_calls.append(kwargs)

    async def send_proposal_approved(self, **kwargs) -> None:
        self.approved_calls.append(kwargs)

    async def send_project_started(self, **kwargs) -> None:
        self.project_started_calls.append(kwargs)

    async def send_project_cancelled(self, **kwargs) -> None:
        self.project_cancelled_calls.append(kwargs)

    async def send_project_completed(self, **kwargs) -> None:
        self.project_completed_calls.append(kwargs)


class RecordingNotificationDispatcher:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def notify(self, **kwargs) -> None:
        self.calls.append(kwargs)

    async def notify_many(self, **kwargs) -> None:
        for recipient_permission_id in kwargs["recipient_permission_ids"]:
            call = {
                key: value
                for key, value in kwargs.items()
                if key != "recipient_permission_ids"
            }
            call["recipient_permission_id"] = recipient_permission_id
            self.calls.append(call)


@asynccontextmanager
async def client_with_repos(
    caller: Actor = _CALLER,
    permission_records: dict[str, PermissionRecord] | None = None,
    requester_provisioner: RecordingRequesterProvisioner | None = None,
    access_email_sender: RecordingAccessEmailSender | None = None,
    proposal_email_sender: RecordingProposalNotificationEmailSender | None = None,
    notification_dispatcher: RecordingNotificationDispatcher | None = None,
    file_storage: object | None = None,
) -> AsyncIterator[
    tuple[
        AsyncClient,
        InMemoryProjectRepository,
        InMemoryProposalRepository,
        InMemoryConversationRepository,
    ]
]:
    project_repo = InMemoryProjectRepository()
    proposal_repo = InMemoryProposalRepository()
    conversation_repo = InMemoryConversationRepository()
    access_log_repo = InMemoryAccessLogRepository()
    occurrence_log_repo = InMemoryOccurrenceLogRepository()
    publication_log_repo = InMemoryPublicationLogRepository()
    file_storage = file_storage or InMemoryFileStorage()
    permission_records = permission_records or {}
    session = CommitOnlySession(permission_records)
    requester_provisioner = requester_provisioner or RecordingRequesterProvisioner()
    access_email_sender = access_email_sender or RecordingAccessEmailSender()
    proposal_email_sender = (
        proposal_email_sender or RecordingProposalNotificationEmailSender()
    )
    notification_dispatcher = (
        notification_dispatcher or RecordingNotificationDispatcher()
    )

    app.dependency_overrides[get_project_repo] = lambda: project_repo
    app.dependency_overrides[get_proposal_repo] = lambda: proposal_repo
    app.dependency_overrides[get_conversation_repo] = lambda: conversation_repo
    app.dependency_overrides[get_access_log_repo] = lambda: access_log_repo
    app.dependency_overrides[get_occurrence_log_repo] = lambda: occurrence_log_repo
    app.dependency_overrides[get_publication_log_repo] = lambda: publication_log_repo
    app.dependency_overrides[get_file_storage] = lambda: file_storage
    app.dependency_overrides[get_async_session] = lambda: session
    app.dependency_overrides[get_caller_permission] = lambda: caller
    app.dependency_overrides[get_reader] = lambda: InMemoryPermissionReader(
        permission_records
    )
    app.dependency_overrides[get_external_requester_provisioner] = lambda: (
        requester_provisioner
    )
    app.dependency_overrides[get_requester_access_email_sender] = lambda: (
        access_email_sender
    )
    app.dependency_overrides[get_proposal_notification_email_sender] = lambda: (
        proposal_email_sender
    )
    app.dependency_overrides[get_reference_number_generator] = lambda: (
        InMemoryReferenceNumberGenerator(proposal_repo)
    )
    app.dependency_overrides[get_notifications_dispatcher] = lambda: (
        notification_dispatcher
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, project_repo, proposal_repo, conversation_repo

    app.dependency_overrides.clear()


async def test_submit_proposal_returns_201() -> None:
    async with client_with_repos() as (client, _, _, _):
        response = await client.post(
            "/api/v1/proposals",
            data={
                "title": "Collection study",
                "intendedUse": "IN_SITU_VISIT",
                "purpose": "To study the collection",
                "beginDate": "2026-06-01",
                "endDate": "2026-06-07",
                "initialMessageSubject": "Collection study",
                "initialMessageBody": "To study the collection",
            },
            headers={"X-Permission-Id": "permission-1"},
        )

    assert response.status_code == 201
    body = response.json()
    assert body["proposal"]["status"] == "SUBMITTED"
    assert body["proposal"]["referenceNumber"].startswith("VRP-")
    assert body["proposal"]["title"] == "Collection study"
    assert body["proposal"]["beginDate"] == "2026-06-01"
    assert body["proposal"]["endDate"] == "2026-06-07"
    assert body["proposal"]["submissionChannel"] == "AUTHENTICATED"
    assert "conversationId" in body


async def test_submit_proposal_notifies_all_staff_except_actor() -> None:
    notification_dispatcher = RecordingNotificationDispatcher()
    proposal_email_sender = RecordingProposalNotificationEmailSender()
    async with client_with_repos(
        caller=_STAFF_CALLER,
        permission_records={
            "permission-staff": _permission_record(
                "permission-staff", GroupName.CURATORIAL
            ),
            "permission-curatorial": _permission_record(
                "permission-curatorial", GroupName.CURATORIAL
            ),
            "permission-collections": _permission_record(
                "permission-collections", GroupName.COLLECTIONS_MANAGEMENT
            ),
            "permission-external": _permission_record(
                "permission-external", GroupName.EXTERNAL
            ),
        },
        notification_dispatcher=notification_dispatcher,
        proposal_email_sender=proposal_email_sender,
    ) as (client, _, _, _):
        response = await client.post(
            "/api/v1/proposals",
            data={
                "title": "Collection study",
                "intendedUse": "IN_SITU_VISIT",
                "purpose": "To study the collection",
                "beginDate": "2026-06-01",
                "endDate": "2026-06-07",
                "initialMessageSubject": "Collection study",
                "initialMessageBody": "To study the collection",
            },
        )

    assert response.status_code == 201
    proposal_id = response.json()["proposal"]["id"]
    assert [
        call["recipient_permission_id"] for call in notification_dispatcher.calls
    ] == ["permission-curatorial", "permission-collections"]
    assert {call["kind"] for call in notification_dispatcher.calls} == {
        "PROPOSAL_SUBMITTED"
    }
    assert {call["related_resource_id"] for call in notification_dispatcher.calls} == {
        proposal_id
    }
    assert [call["to_email"] for call in proposal_email_sender.submitted_calls] == [
        "permission-curatorial@example.org",
        "permission-collections@example.org",
    ]
    submitted_by_names = {
        call["submitted_by_name"] for call in proposal_email_sender.submitted_calls
    }
    assert submitted_by_names == {"User permission-staff"}


async def test_submit_proposal_dedupes_broadcast_email_by_user_not_notifications() -> (
    None
):
    notification_dispatcher = RecordingNotificationDispatcher()
    proposal_email_sender = RecordingProposalNotificationEmailSender()
    async with client_with_repos(
        caller=_STAFF_CALLER,
        permission_records={
            "permission-staff": _permission_record(
                "permission-staff", GroupName.CURATORIAL
            ),
            "permission-bob-curatorial": _permission_record(
                "permission-bob-curatorial",
                GroupName.CURATORIAL,
                user_id="user-bob",
                user_name="Bob Santos",
                user_email="bob@example.org",
            ),
            "permission-bob-collections": _permission_record(
                "permission-bob-collections",
                GroupName.COLLECTIONS_MANAGEMENT,
                user_id="user-bob",
                user_name="Bob Santos",
                user_email="bob@example.org",
            ),
            "permission-bob-direction": _permission_record(
                "permission-bob-direction",
                GroupName.DIRECTION,
                user_id="user-bob",
                user_name="Bob Santos",
                user_email="bob@example.org",
            ),
            "permission-bob-admin": _permission_record(
                "permission-bob-admin",
                GroupName.SYS_ADMIN,
                user_id="user-bob",
                user_name="Bob Santos",
                user_email="bob@example.org",
            ),
        },
        notification_dispatcher=notification_dispatcher,
        proposal_email_sender=proposal_email_sender,
    ) as (client, _, _, _):
        response = await client.post(
            "/api/v1/proposals",
            data={
                "title": "Collection study",
                "intendedUse": "IN_SITU_VISIT",
                "purpose": "To study the collection",
                "beginDate": "2026-06-01",
                "endDate": "2026-06-07",
                "initialMessageSubject": "Collection study",
                "initialMessageBody": "To study the collection",
            },
        )

    assert response.status_code == 201
    assert [
        call["recipient_permission_id"] for call in notification_dispatcher.calls
    ] == [
        "permission-bob-curatorial",
        "permission-bob-collections",
        "permission-bob-direction",
        "permission-bob-admin",
    ]
    assert [call["to_email"] for call in proposal_email_sender.submitted_calls] == [
        "bob@example.org"
    ]
    assert [
        call["recipient_name"] for call in proposal_email_sender.submitted_calls
    ] == ["Bob Santos"]


async def test_submit_proposal_carries_intended_use_through_to_detail() -> None:
    async with client_with_repos() as (client, _, _, _):
        created = await client.post(
            "/api/v1/proposals",
            data={
                "title": "Collection study",
                "intendedUse": "EXHIBITION",
                "purpose": "To exhibit the collection",
                "beginDate": "2026-06-01",
                "endDate": "2026-06-07",
                "initialMessageSubject": "Collection study",
                "initialMessageBody": "To exhibit the collection",
            },
            headers={"X-Permission-Id": "permission-1"},
        )
        proposal_id = created.json()["proposal"]["id"]
        detail = await client.get(
            f"/api/v1/proposals/{proposal_id}",
            headers={"X-Permission-Id": "permission-1"},
        )

    assert created.status_code == 201
    assert created.json()["proposal"]["intendedUse"] == "EXHIBITION"
    # The use type survives the round-trip through the repository.
    assert detail.status_code == 200
    assert detail.json()["intendedUse"] == "EXHIBITION"


async def test_submit_proposal_invalid_date_range_returns_422() -> None:
    async with client_with_repos() as (client, _, _, _):
        response = await client.post(
            "/api/v1/proposals",
            data={
                "title": "Collection study",
                "intendedUse": "IN_SITU_VISIT",
                "purpose": "To study the collection",
                "beginDate": "2026-06-07",
                "endDate": "2026-06-01",
                "initialMessageSubject": "Collection study",
                "initialMessageBody": "To study the collection",
            },
            headers={"X-Permission-Id": "permission-1"},
        )

    assert response.status_code == 422
    assert response.json()["message"] == "endDate must be after beginDate"


async def test_submit_proposal_accepts_supporting_document_types() -> None:
    storage = InMemoryFileStorage()
    async with client_with_repos(file_storage=storage) as (
        client,
        _,
        proposal_repo,
        _,
    ):
        response = await client.post(
            "/api/v1/proposals",
            data={
                "title": "Collection study",
                "intendedUse": "IN_SITU_VISIT",
                "beginDate": "2026-06-01",
                "endDate": "2026-06-07",
                "initialMessageSubject": "Collection study",
                "initialMessageBody": "To study the collection",
            },
            files=[
                ("documents", ("support.pdf", b"%PDF-1.4\n", "application/pdf")),
                ("documents", ("photo.jpg", b"\xff\xd8\xff\xe0", "image/jpeg")),
                ("documents", ("scan.png", b"\x89PNG\r\n\x1a\n", "image/png")),
                (
                    "documents",
                    (
                        "letter.docx",
                        _docx_bytes(),
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    ),
                ),
            ],
            headers={"X-Permission-Id": "permission-1"},
        )

        proposal_id = response.json()["proposal"]["id"]
        saved_proposal = await proposal_repo.get_by_id(ProposalId(proposal_id))

    assert response.status_code == 201
    assert saved_proposal is not None
    assert [document.file_name for document in saved_proposal.documents] == [
        "support.pdf",
        "photo.jpg",
        "scan.png",
        "letter.docx",
    ]
    assert {document.type.value for document in saved_proposal.documents} == {
        "REQUESTER_ATTACHMENT"
    }
    assert {document.submitted_by for document in saved_proposal.documents} == {
        "permission-1"
    }
    assert len(storage.files) == 4


async def test_submit_proposal_rejects_unsupported_document_type() -> None:
    async with client_with_repos() as (client, _, _, _):
        response = await client.post(
            "/api/v1/proposals",
            data={
                "intendedUse": "IN_SITU_VISIT",
                "beginDate": "2026-06-01",
                "endDate": "2026-06-07",
                "initialMessageSubject": "Collection study",
                "initialMessageBody": "To study the collection",
            },
            files=[
                ("documents", ("notes.txt", b"plain text", "text/plain")),
            ],
            headers={"X-Permission-Id": "permission-1"},
        )

    assert response.status_code == 415
    assert response.json()["error"] == "UNSUPPORTED_FILE_TYPE"


async def test_submit_proposal_rejects_more_than_five_documents() -> None:
    async with client_with_repos() as (client, _, _, _):
        response = await client.post(
            "/api/v1/proposals",
            data={
                "intendedUse": "IN_SITU_VISIT",
                "beginDate": "2026-06-01",
                "endDate": "2026-06-07",
                "initialMessageSubject": "Collection study",
                "initialMessageBody": "To study the collection",
            },
            files=[
                (
                    "documents",
                    (f"support-{index}.pdf", b"%PDF-1.4\n", "application/pdf"),
                )
                for index in range(6)
            ],
            headers={"X-Permission-Id": "permission-1"},
        )

    assert response.status_code == 422
    assert response.json()["errors"][0]["field"] == "documents"


async def test_submit_proposal_rejects_oversized_document() -> None:
    async with client_with_repos() as (client, _, _, _):
        response = await client.post(
            "/api/v1/proposals",
            data={
                "intendedUse": "IN_SITU_VISIT",
                "beginDate": "2026-06-01",
                "endDate": "2026-06-07",
                "initialMessageSubject": "Collection study",
                "initialMessageBody": "To study the collection",
            },
            files=[
                (
                    "documents",
                    (
                        "large.pdf",
                        b"%PDF-1.4\n" + b"x" * (10 * 1024 * 1024),
                        "application/pdf",
                    ),
                ),
            ],
            headers={"X-Permission-Id": "permission-1"},
        )

    assert response.status_code == 413
    assert response.json()["error"] == "FILE_TOO_LARGE"


async def test_submit_proposal_rolls_back_saved_documents_when_upload_fails() -> None:
    storage = FailingSecondSaveStorage()
    async with client_with_repos(file_storage=storage) as (client, _, _, _):
        with pytest.raises(RuntimeError, match="storage failed"):
            await client.post(
                "/api/v1/proposals",
                data={
                    "intendedUse": "IN_SITU_VISIT",
                    "beginDate": "2026-06-01",
                    "endDate": "2026-06-07",
                    "initialMessageSubject": "Collection study",
                    "initialMessageBody": "To study the collection",
                },
                files=[
                    (
                        "documents",
                        ("support-1.pdf", b"%PDF-1.4\n", "application/pdf"),
                    ),
                    (
                        "documents",
                        ("support-2.pdf", b"%PDF-1.4\n", "application/pdf"),
                    ),
                ],
                headers={"X-Permission-Id": "permission-1"},
            )

    assert storage.files == {}


async def test_list_proposals_serializes_populated_item() -> None:
    async with client_with_repos() as (client, _, proposal_repo, _):
        await proposal_repo.add(
            Proposal(
                id=ProposalId("prop-1"),
                reference_number=ReferenceNumber("VRP-20260601-0001"),
                title="Proposal title",
                collection_use_project_id="proj-1",
                intended_use=UseType.IN_SITU_VISIT,
                begin_date=date(2026, 6, 1),
                end_date=date(2026, 6, 7),
                status=ProposalStatus.SUBMITTED,
                requested_by=PermissionId("permission-1"),
                submitted_at=datetime(2026, 6, 7, tzinfo=UTC),
                submission_channel=SubmissionChannel.AUTHENTICATED,
            )
        )

        response = await client.get(
            "/api/v1/proposals",
            headers={"X-Permission-Id": "permission-1"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["totalElements"] == 1
    item = body["content"][0]
    assert item["id"] == "prop-1"
    assert item["referenceNumber"] == "VRP-20260601-0001"
    assert item["title"] == "Proposal title"
    assert item["status"] == "SUBMITTED"
    assert item["intendedUse"] == "IN_SITU_VISIT"
    assert item["submissionChannel"] == "AUTHENTICATED"


async def test_list_proposals_paginates_results() -> None:
    async with client_with_repos() as (client, _, proposal_repo, _):
        for index in range(3):
            await proposal_repo.add(
                Proposal(
                    id=ProposalId(f"prop-{index + 1}"),
                    reference_number=ReferenceNumber(f"VRP-20260601-{index + 1:04d}"),
                    title=f"Proposal {index + 1}",
                    collection_use_project_id=CollectionUseProjectId(
                        f"proj-{index + 1}"
                    ),
                    intended_use=UseType.IN_SITU_VISIT,
                    begin_date=date(2026, 6, 1),
                    end_date=date(2026, 6, 7),
                    status=ProposalStatus.SUBMITTED,
                    requested_by=PermissionId("permission-1"),
                    submitted_at=datetime(2026, 6, 7, index, tzinfo=UTC),
                    submission_channel=SubmissionChannel.AUTHENTICATED,
                )
            )

        response = await client.get(
            "/api/v1/proposals?page=1&size=2",
            headers={"X-Permission-Id": "permission-1"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["page"] == 1
    assert body["size"] == 2
    assert body["totalElements"] == 3
    assert body["totalPages"] == 2
    assert [item["id"] for item in body["content"]] == ["prop-3"]


async def test_list_proposals_filters_by_multiple_statuses() -> None:
    async with client_with_repos() as (client, _, proposal_repo, _):
        for proposal_id, status in (
            ("rejected", ProposalStatus.REJECTED),
            ("cancelled", ProposalStatus.CANCELLED),
            ("pending", ProposalStatus.PENDING),
        ):
            proposal = _proposal(proposal_id=proposal_id, status=status)
            proposal.reference_number = ReferenceNumber(
                f"VRP-20260601-{len(proposal_repo.items) + 1:04d}"
            )
            await proposal_repo.add(proposal)

        response = await client.get(
            "/api/v1/proposals?status=REJECTED&status=CANCELLED&page=0&size=100",
            headers={"X-Permission-Id": "permission-1"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["totalElements"] == 2
    assert {item["status"] for item in body["content"]} == {
        "REJECTED",
        "CANCELLED",
    }


async def test_get_proposal_not_found_returns_404() -> None:
    async with client_with_repos() as (client, _, _, _):
        response = await client.get(
            "/api/v1/proposals/nonexistent-id",
            headers={"X-Permission-Id": "permission-1"},
        )

    assert response.status_code == 404


async def test_relate_searched_objects_surfaces_them_on_detail() -> None:
    # A proposal is created object-free; the researcher later searches the
    # catalog and relates the matches via POST /requested-objects, supplying the
    # full inventory snapshot from the search result.
    async with client_with_repos() as (client, _, proposal_repo, _):
        create = await client.post(
            "/api/v1/proposals",
            data={
                "title": "Manuscript study",
                "intendedUse": "IN_SITU_VISIT",
                "purpose": "To study the manuscript",
                "beginDate": "2026-06-01",
                "endDate": "2026-06-07",
                "initialMessageSubject": "Manuscript study",
                "initialMessageBody": "To study the manuscript",
            },
            headers={"X-Permission-Id": "permission-1"},
        )
        assert create.status_code == 201
        proposal_id = create.json()["proposal"]["id"]

        related = await client.post(
            f"/api/v1/proposals/{proposal_id}/requested-objects",
            json={
                "objects": [
                    {
                        "inventoryNumber": "INV-001",
                        "displayTitle": "Book of Hours",
                        "objectName": "Illuminated manuscript",
                        "collectionId": "collection-manuscripts",
                        "collectionName": "Manuscripts",
                        "category": "manuscript",
                    }
                ]
            },
            headers={"X-Permission-Id": "permission-1"},
        )
        assert related.status_code == 201

        detail = await client.get(
            f"/api/v1/proposals/{proposal_id}",
            headers={"X-Permission-Id": "permission-1"},
        )

    assert detail.status_code == 200
    body = detail.json()
    assert body["referenceNumber"].startswith("VRP-")
    assert body["title"] == "Manuscript study"
    objects = body["requestedObjects"]
    assert len(objects) == 1
    assert objects[0]["inventoryNumber"] == "INV-001"
    assert objects[0]["displayTitle"] == "Book of Hours"
    assert objects[0]["objectName"] == "Illuminated manuscript"
    assert objects[0]["collectionId"] == "collection-manuscripts"
    assert objects[0]["collectionName"] == "Manuscripts"
    assert objects[0]["category"] == "manuscript"
    assert objects[0]["requestedBy"] is None


async def test_remove_requested_object_updates_proposal_detail() -> None:
    async with client_with_repos() as (client, _, _, _):
        create = await client.post(
            "/api/v1/proposals",
            data={
                "title": "Manuscript study",
                "intendedUse": "IN_SITU_VISIT",
                "purpose": "To study the manuscript",
                "beginDate": "2026-06-01",
                "endDate": "2026-06-07",
                "initialMessageSubject": "Manuscript study",
                "initialMessageBody": "To study the manuscript",
            },
            headers={"X-Permission-Id": "permission-1"},
        )
        assert create.status_code == 201
        proposal_id = create.json()["proposal"]["id"]

        related = await client.post(
            f"/api/v1/proposals/{proposal_id}/requested-objects",
            json={
                "objects": [
                    {
                        "inventoryNumber": "INV-001",
                        "displayTitle": "Book of Hours",
                        "objectName": "Illuminated manuscript",
                    }
                ]
            },
            headers={"X-Permission-Id": "permission-1"},
        )
        assert related.status_code == 201
        requested_object_id = related.json()["requestedObjects"][0]["id"]

        removed = await client.delete(
            f"/api/v1/proposals/{proposal_id}/requested-objects/{requested_object_id}",
            headers={"X-Permission-Id": "permission-1"},
        )
        detail = await client.get(
            f"/api/v1/proposals/{proposal_id}",
            headers={"X-Permission-Id": "permission-1"},
        )

    assert removed.status_code == 204
    assert detail.status_code == 200
    assert detail.json()["requestedObjects"] == []


async def test_external_user_cannot_read_other_proposal_events() -> None:
    async with client_with_repos() as (client, _, proposal_repo, _):
        await proposal_repo.add(
            Proposal(
                id=ProposalId("prop-foreign"),
                reference_number=ReferenceNumber("VRP-20260601-0001"),
                title="Proposal title",
                collection_use_project_id=CollectionUseProjectId("proj-foreign"),
                intended_use=UseType.IN_SITU_VISIT,
                begin_date=date(2026, 6, 1),
                end_date=date(2026, 6, 7),
                status=ProposalStatus.SUBMITTED,
                requested_by=PermissionId("permission-other"),
                submitted_at=datetime(2026, 6, 7, tzinfo=UTC),
                submission_channel=SubmissionChannel.AUTHENTICATED,
            )
        )

        response = await client.get(
            "/api/v1/proposals/prop-foreign/events",
            headers={"X-Permission-Id": "permission-1"},
        )

    assert response.status_code == 403
    assert response.json()["error"] == "ACCESS_DENIED"


async def test_external_user_cannot_read_other_proposal_documents() -> None:
    async with client_with_repos() as (client, _, proposal_repo, _):
        await proposal_repo.add(
            Proposal(
                id=ProposalId("prop-foreign"),
                reference_number=ReferenceNumber("VRP-20260601-0001"),
                title="Proposal title",
                collection_use_project_id=CollectionUseProjectId("proj-foreign"),
                intended_use=UseType.IN_SITU_VISIT,
                begin_date=date(2026, 6, 1),
                end_date=date(2026, 6, 7),
                status=ProposalStatus.SUBMITTED,
                requested_by=PermissionId("permission-other"),
                submitted_at=datetime(2026, 6, 7, tzinfo=UTC),
                submission_channel=SubmissionChannel.AUTHENTICATED,
            )
        )

        response = await client.get(
            "/api/v1/proposals/prop-foreign/documents",
            headers={"X-Permission-Id": "permission-1"},
        )

    assert response.status_code == 403
    assert response.json()["error"] == "ACCESS_DENIED"


async def test_external_user_cannot_read_other_project_events() -> None:
    async with client_with_repos() as (client, project_repo, proposal_repo, _):
        await project_repo.add(
            CollectionUseProject(
                id=CollectionUseProjectId("proj-foreign"),
                reference_number=ReferenceNumber("CUP-ABCDEFG1"),
                title="Foreign project",
                purpose="Restricted",
                intended_use=UseType.IN_SITU_VISIT,
                status=UseStatus.CREATED,
                begin_date=date(2026, 6, 1),
                end_date=date(2026, 6, 7),
                requested_by=PermissionId("permission-other"),
            )
        )
        await proposal_repo.add(
            Proposal(
                id=ProposalId("prop-foreign"),
                reference_number=ReferenceNumber("VRP-20260601-0001"),
                title="Proposal title",
                collection_use_project_id=CollectionUseProjectId("proj-foreign"),
                intended_use=UseType.IN_SITU_VISIT,
                begin_date=date(2026, 6, 1),
                end_date=date(2026, 6, 7),
                status=ProposalStatus.APPROVED,
                requested_by=PermissionId("permission-other"),
                submitted_at=datetime(2026, 6, 7, tzinfo=UTC),
                submission_channel=SubmissionChannel.AUTHENTICATED,
            )
        )

        response = await client.get(
            "/api/v1/collection-use-projects/proj-foreign/events",
            headers={"X-Permission-Id": "permission-1"},
        )

    assert response.status_code == 403
    assert response.json()["error"] == "ACCESS_DENIED"


async def test_list_projects_applies_search_filter() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        project_repo,
        _,
        _,
    ):
        await project_repo.add(
            CollectionUseProject(
                id=CollectionUseProjectId("project-alpha"),
                reference_number=ReferenceNumber("CUP-ALPHA001"),
                title="Alpha manuscripts",
                purpose="Visible",
                intended_use=UseType.IN_SITU_VISIT,
                status=UseStatus.CREATED,
                begin_date=date(2026, 6, 1),
                end_date=date(2026, 6, 7),
                requested_by=PermissionId("permission-1"),
            )
        )
        await project_repo.add(
            CollectionUseProject(
                id=CollectionUseProjectId("project-beta"),
                reference_number=ReferenceNumber("CUP-BETA0001"),
                title="Beta paintings",
                purpose="Hidden by search",
                intended_use=UseType.IN_SITU_VISIT,
                status=UseStatus.CREATED,
                begin_date=date(2026, 6, 1),
                end_date=date(2026, 6, 7),
                requested_by=PermissionId("permission-1"),
            )
        )

        response = await client.get("/api/v1/collection-use-projects?search=alpha")

    assert response.status_code == 200
    body = response.json()
    assert body["totalElements"] == 1
    assert body["content"][0]["id"] == "project-alpha"


async def test_staff_can_scope_list_with_requested_by() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        project_repo,
        _,
        _,
    ):
        await project_repo.add(
            _project("mine", requested_by=PermissionId("permission-staff"))
        )
        await project_repo.add(
            _project("theirs", requested_by=PermissionId("permission-other"))
        )

        scoped = await client.get(
            "/api/v1/collection-use-projects?requestedBy=permission-staff",
            headers={"X-Permission-Id": "permission-staff"},
        )
        unscoped = await client.get(
            "/api/v1/collection-use-projects",
            headers={"X-Permission-Id": "permission-staff"},
        )

    assert scoped.status_code == 200
    scoped_body = scoped.json()
    assert scoped_body["totalElements"] == 1
    assert scoped_body["content"][0]["id"] == "mine"
    # Without the filter, staff still see every project.
    assert unscoped.json()["totalElements"] == 2


async def test_non_staff_requested_by_is_ignored_and_forced_to_own_id() -> None:
    async with client_with_repos(caller=_CALLER) as (
        client,
        project_repo,
        _,
        _,
    ):
        await project_repo.add(
            _project("mine", requested_by=PermissionId("permission-1"))
        )
        await project_repo.add(
            _project("theirs", requested_by=PermissionId("permission-other"))
        )

        # A non-staff caller tries to see someone else's projects.
        response = await client.get(
            "/api/v1/collection-use-projects?requestedBy=permission-other",
            headers={"X-Permission-Id": "permission-1"},
        )

    assert response.status_code == 200
    body = response.json()
    # The spoofed filter is ignored; the list stays scoped to the caller's id.
    assert body["totalElements"] == 1
    assert body["content"][0]["id"] == "mine"


async def test_list_projects_applies_date_filters() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        project_repo,
        _,
        _,
    ):
        await project_repo.add(
            CollectionUseProject(
                id=CollectionUseProjectId("project-june"),
                reference_number=ReferenceNumber("CUP-JUNE0001"),
                title="June project",
                purpose="Visible",
                intended_use=UseType.IN_SITU_VISIT,
                status=UseStatus.CREATED,
                begin_date=date(2026, 6, 10),
                end_date=date(2026, 6, 12),
                requested_by=PermissionId("permission-1"),
            )
        )
        await project_repo.add(
            CollectionUseProject(
                id=CollectionUseProjectId("project-july"),
                reference_number=ReferenceNumber("CUP-JULY0001"),
                title="July project",
                purpose="Hidden by dates",
                intended_use=UseType.IN_SITU_VISIT,
                status=UseStatus.CREATED,
                begin_date=date(2026, 7, 10),
                end_date=date(2026, 7, 12),
                requested_by=PermissionId("permission-1"),
            )
        )

        response = await client.get(
            "/api/v1/collection-use-projects?dateFrom=2026-06-01&dateTo=2026-06-30"
        )

    assert response.status_code == 200
    body = response.json()
    assert body["totalElements"] == 1
    assert body["content"][0]["id"] == "project-june"


async def test_external_owner_cannot_assign_proposal() -> None:
    async with client_with_repos() as (client, _, proposal_repo, _):
        await proposal_repo.add(
            Proposal(
                id=ProposalId("prop-1"),
                reference_number=ReferenceNumber("VRP-20260601-0001"),
                title="Proposal title",
                collection_use_project_id=CollectionUseProjectId("proj-1"),
                intended_use=UseType.IN_SITU_VISIT,
                begin_date=date(2026, 6, 1),
                end_date=date(2026, 6, 7),
                status=ProposalStatus.SUBMITTED,
                requested_by=PermissionId("permission-1"),
                submitted_at=datetime(2026, 6, 7, tzinfo=UTC),
                submission_channel=SubmissionChannel.AUTHENTICATED,
            )
        )

        response = await client.post(
            "/api/v1/proposals/prop-1/assign",
            json={},
            headers={"X-Permission-Id": "permission-1"},
        )

    assert response.status_code == 403
    assert response.json()["error"] == "INSUFFICIENT_GROUP"


async def test_external_owner_cannot_request_documents() -> None:
    async with client_with_repos() as (client, _, proposal_repo, _):
        await proposal_repo.add(
            Proposal(
                id=ProposalId("prop-1"),
                reference_number=ReferenceNumber("VRP-20260601-0001"),
                title="Proposal title",
                collection_use_project_id=CollectionUseProjectId("proj-1"),
                intended_use=UseType.IN_SITU_VISIT,
                begin_date=date(2026, 6, 1),
                end_date=date(2026, 6, 7),
                status=ProposalStatus.PENDING,
                requested_by=PermissionId("permission-1"),
                submitted_at=datetime(2026, 6, 7, tzinfo=UTC),
                submission_channel=SubmissionChannel.AUTHENTICATED,
            )
        )

        response = await client.post(
            "/api/v1/proposals/prop-1/request-documents",
            json={
                "requiredDocuments": [
                    {"type": "insurance", "description": "Insurance proof"}
                ]
            },
            headers={"X-Permission-Id": "permission-1"},
        )

    assert response.status_code == 403
    assert response.json()["error"] == "INSUFFICIENT_GROUP"


async def test_assign_proposal_rejects_unknown_target_permission() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        _,
        proposal_repo,
        _,
    ):
        await proposal_repo.add(
            Proposal(
                id=ProposalId("prop-1"),
                reference_number=ReferenceNumber("VRP-20260601-0001"),
                title="Proposal title",
                collection_use_project_id=CollectionUseProjectId("proj-1"),
                intended_use=UseType.IN_SITU_VISIT,
                begin_date=date(2026, 6, 1),
                end_date=date(2026, 6, 7),
                status=ProposalStatus.SUBMITTED,
                requested_by=PermissionId("permission-1"),
                submitted_at=datetime(2026, 6, 7, tzinfo=UTC),
                submission_channel=SubmissionChannel.AUTHENTICATED,
            )
        )

        response = await client.post(
            "/api/v1/proposals/prop-1/assign",
            json={"targetPermissionId": "missing-permission"},
        )

    assert response.status_code == 404
    assert response.json()["error"] == "PERMISSION_NOT_FOUND"


async def test_assign_proposal_rejects_external_target_permission() -> None:
    async with client_with_repos(
        caller=_STAFF_CALLER,
        permission_records={
            "permission-external": _permission_record(
                "permission-external", GroupName.EXTERNAL
            )
        },
    ) as (client, _, proposal_repo, _):
        await proposal_repo.add(
            Proposal(
                id=ProposalId("prop-1"),
                reference_number=ReferenceNumber("VRP-20260601-0001"),
                title="Proposal title",
                collection_use_project_id=CollectionUseProjectId("proj-1"),
                intended_use=UseType.IN_SITU_VISIT,
                begin_date=date(2026, 6, 1),
                end_date=date(2026, 6, 7),
                status=ProposalStatus.SUBMITTED,
                requested_by=PermissionId("permission-1"),
                submitted_at=datetime(2026, 6, 7, tzinfo=UTC),
                submission_channel=SubmissionChannel.AUTHENTICATED,
            )
        )

        response = await client.post(
            "/api/v1/proposals/prop-1/assign",
            json={"targetPermissionId": "permission-external"},
        )

    assert response.status_code == 422
    assert response.json()["error"] == "INVALID_PERMISSION_TARGET"


async def test_forward_proposal_rejects_external_target_permission() -> None:
    async with client_with_repos(
        caller=_STAFF_CALLER,
        permission_records={
            "permission-external": _permission_record(
                "permission-external", GroupName.EXTERNAL
            )
        },
    ) as (client, _, proposal_repo, _):
        await proposal_repo.add(
            Proposal(
                id=ProposalId("prop-1"),
                reference_number=ReferenceNumber("VRP-20260601-0001"),
                title="Proposal title",
                collection_use_project_id=CollectionUseProjectId("proj-1"),
                intended_use=UseType.IN_SITU_VISIT,
                begin_date=date(2026, 6, 1),
                end_date=date(2026, 6, 7),
                status=ProposalStatus.PENDING,
                requested_by=PermissionId("permission-1"),
                submitted_at=datetime(2026, 6, 7, tzinfo=UTC),
                submission_channel=SubmissionChannel.AUTHENTICATED,
            )
        )

        response = await client.post(
            "/api/v1/proposals/prop-1/forward",
            json={"targetPermissionId": "permission-external"},
        )

    assert response.status_code == 422
    assert response.json()["error"] == "INVALID_PERMISSION_TARGET"


async def test_reject_proposal_creates_message_to_requester() -> None:
    proposal_email_sender = RecordingProposalNotificationEmailSender()
    async with client_with_repos(
        caller=_STAFF_CALLER,
        permission_records={
            "permission-1": _permission_record("permission-1", GroupName.EXTERNAL)
        },
        proposal_email_sender=proposal_email_sender,
    ) as (client, _, proposal_repo, conversation_repo):
        proposal = Proposal(
            id=ProposalId("prop-1"),
            reference_number=ReferenceNumber("VRP-20260601-0001"),
            title="Proposal title",
            collection_use_project_id=CollectionUseProjectId("proj-1"),
            intended_use=UseType.IN_SITU_VISIT,
            begin_date=date(2026, 6, 1),
            end_date=date(2026, 6, 7),
            status=ProposalStatus.PENDING,
            requested_by=PermissionId("permission-1"),
            submitted_at=datetime(2026, 6, 7, tzinfo=UTC),
            submission_channel=SubmissionChannel.AUTHENTICATED,
        )
        await proposal_repo.add(proposal)
        await conversation_repo.add(
            Conversation.start(
                id=ConversationId("conv-1"),
                proposal_id=proposal.id,
                initial_message=Message(
                    id=MessageId("message-1"),
                    sent_at=datetime(2026, 6, 7, tzinfo=UTC),
                    sender=EmailAddress("permission-1@example.org"),
                    recipient=EmailAddress("collections@museum.pt"),
                    subject="Initial",
                    body="Initial message",
                ),
            )
        )

        response = await client.post(
            "/api/v1/proposals/prop-1/reject",
            json={"reason": "The request is outside the collection policy."},
        )
        saved_conversation = await conversation_repo.get_by_proposal_id(proposal.id)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "REJECTED"
    assert saved_conversation is not None
    message = saved_conversation.messages[-1]
    assert message.sender.value == "staff@example.org"
    assert message.recipient.value == "permission-1@example.org"
    assert message.body == "The request is outside the collection policy."
    assert proposal_email_sender.rejected_calls == [
        {
            "to_email": "permission-1@example.org",
            "requester_name": "User permission-1",
            "proposal_reference": "VRP-20260601-0001",
            "rejected_by_name": "staff@example.org",
            "reason": "The request is outside the collection policy.",
            "link": f"{settings.public_origin}/p/collections/proposals/prop-1",
        }
    ]


async def test_staff_can_assign_proposal_to_staff_target() -> None:
    notification_dispatcher = RecordingNotificationDispatcher()
    proposal_email_sender = RecordingProposalNotificationEmailSender()
    async with client_with_repos(
        caller=_STAFF_CALLER,
        permission_records={
            "permission-staff": _permission_record(
                "permission-staff", GroupName.CURATORIAL
            ),
            "permission-target": _permission_record(
                "permission-target", GroupName.COLLECTIONS_MANAGEMENT
            ),
        },
        notification_dispatcher=notification_dispatcher,
        proposal_email_sender=proposal_email_sender,
    ) as (client, _, proposal_repo, _):
        await proposal_repo.add(
            Proposal(
                id=ProposalId("prop-1"),
                reference_number=ReferenceNumber("VRP-20260601-0001"),
                title="Proposal title",
                collection_use_project_id=CollectionUseProjectId("proj-1"),
                intended_use=UseType.IN_SITU_VISIT,
                begin_date=date(2026, 6, 1),
                end_date=date(2026, 6, 7),
                status=ProposalStatus.SUBMITTED,
                requested_by=PermissionId("permission-1"),
                submitted_at=datetime(2026, 6, 7, tzinfo=UTC),
                submission_channel=SubmissionChannel.AUTHENTICATED,
            )
        )

        response = await client.post(
            "/api/v1/proposals/prop-1/assign",
            json={"targetPermissionId": "permission-target", "note": "Please triage"},
        )
        proposal = await proposal_repo.get_by_id(ProposalId("prop-1"))

    assert response.status_code == 200
    body = response.json()
    assert body["assignedTo"]["permissionId"] == "permission-target"
    assert body["lastEvent"]["triggeredBy"]["permissionId"] == "permission-staff"
    assert proposal is not None
    assert proposal.assigned_to == "permission-target"
    assert proposal.status == ProposalStatus.PENDING
    assert notification_dispatcher.calls == [
        {
            "recipient_permission_id": "permission-target",
            "kind": "PROPOSAL_ASSIGNED",
            "triggered_by": "permission-staff",
            "related_resource_type": "PROPOSAL",
            "related_resource_id": "prop-1",
            "related_resource_label": "VRP-20260601-0001",
            "note": "Please triage",
        }
    ]
    assert proposal_email_sender.assigned_calls == [
        {
            "to_email": "permission-target@example.org",
            "recipient_name": "User permission-target",
            "proposal_reference": "VRP-20260601-0001",
            "assigned_by_name": "User permission-staff",
            "note": "Please triage",
            "link": f"{settings.public_origin}/p/collections/proposals/prop-1",
        }
    ]
    assert proposal_email_sender.forwarded_calls == []


async def test_staff_can_forward_proposal_to_staff_target() -> None:
    notification_dispatcher = RecordingNotificationDispatcher()
    proposal_email_sender = RecordingProposalNotificationEmailSender()
    async with client_with_repos(
        caller=_STAFF_CALLER,
        permission_records={
            "permission-staff": _permission_record(
                "permission-staff", GroupName.CURATORIAL
            ),
            "permission-target": _permission_record(
                "permission-target", GroupName.COLLECTIONS_MANAGEMENT
            ),
        },
        notification_dispatcher=notification_dispatcher,
        proposal_email_sender=proposal_email_sender,
    ) as (client, _, proposal_repo, _):
        await proposal_repo.add(
            Proposal(
                id=ProposalId("prop-1"),
                reference_number=ReferenceNumber("VRP-20260601-0001"),
                title="Proposal title",
                collection_use_project_id=CollectionUseProjectId("proj-1"),
                intended_use=UseType.IN_SITU_VISIT,
                begin_date=date(2026, 6, 1),
                end_date=date(2026, 6, 7),
                status=ProposalStatus.PENDING,
                requested_by=PermissionId("permission-1"),
                submitted_at=datetime(2026, 6, 7, tzinfo=UTC),
                submission_channel=SubmissionChannel.AUTHENTICATED,
            )
        )

        response = await client.post(
            "/api/v1/proposals/prop-1/forward",
            json={"targetPermissionId": "permission-target", "note": "Direction call"},
        )
        proposal = await proposal_repo.get_by_id(ProposalId("prop-1"))

    assert response.status_code == 200
    assert response.json()["assignedTo"]["permissionId"] == "permission-target"
    assert proposal is not None
    assert proposal.assigned_to == "permission-target"
    assert notification_dispatcher.calls == [
        {
            "recipient_permission_id": "permission-target",
            "kind": "PROPOSAL_FORWARDED",
            "triggered_by": "permission-staff",
            "related_resource_type": "PROPOSAL",
            "related_resource_id": "prop-1",
            "related_resource_label": "VRP-20260601-0001",
            "note": "Direction call",
        }
    ]
    assert proposal_email_sender.forwarded_calls == [
        {
            "to_email": "permission-target@example.org",
            "recipient_name": "User permission-target",
            "proposal_reference": "VRP-20260601-0001",
            "forwarded_by_name": "User permission-staff",
            "note": "Direction call",
            "link": f"{settings.public_origin}/p/collections/proposals/prop-1",
        }
    ]
    assert proposal_email_sender.assigned_calls == []


async def test_curator_can_refer_assigned_proposal_to_direction() -> None:
    notification_dispatcher = RecordingNotificationDispatcher()
    async with client_with_repos(
        caller=_STAFF_CALLER,
        permission_records={
            "permission-staff": _permission_record(
                "permission-staff", GroupName.CURATORIAL
            ),
            "permission-direction": _permission_record(
                "permission-direction", GroupName.DIRECTION
            ),
        },
        notification_dispatcher=notification_dispatcher,
    ) as (client, _, proposal_repo, _):
        proposal = _proposal()
        proposal.assigned_to = PermissionId("permission-staff")
        await proposal_repo.add(proposal)

        response = await client.post(
            "/api/v1/proposals/prop-1/refer-to-direction",
            json={
                "targetPermissionId": "permission-direction",
                "reason": "Strategic decision required",
            },
        )
        saved = await proposal_repo.get_by_id(ProposalId("prop-1"))

    assert response.status_code == 200
    body = response.json()
    assert body["assignedTo"]["permissionId"] == "permission-direction"
    assert body["lastEvent"]["type"] == "REFERRED_TO_DIRECTION"
    assert body["lastEvent"]["note"] == "Strategic decision required"
    assert body["lastEvent"]["targetPermission"]["permissionId"] == (
        "permission-direction"
    )
    assert saved is not None
    assert saved.assigned_to == PermissionId("permission-direction")
    assert notification_dispatcher.calls == [
        {
            "recipient_permission_id": "permission-direction",
            "kind": "PROPOSAL_REFERRED_TO_DIRECTION",
            "triggered_by": "permission-staff",
            "related_resource_type": "PROPOSAL",
            "related_resource_id": "prop-1",
            "related_resource_label": "VRP-20260601-0001",
            "note": "Strategic decision required",
        }
    ]


async def test_direction_can_return_proposal_to_staff_with_required_reason() -> None:
    direction_caller = Actor(
        id=PermissionId("permission-direction"),
        group=GroupName.DIRECTION,
        email="direction@example.org",
    )
    notification_dispatcher = RecordingNotificationDispatcher()
    async with client_with_repos(
        caller=direction_caller,
        permission_records={
            "permission-direction": _permission_record(
                "permission-direction", GroupName.DIRECTION
            ),
            "permission-target": _permission_record(
                "permission-target", GroupName.COLLECTIONS_MANAGEMENT
            ),
        },
        notification_dispatcher=notification_dispatcher,
    ) as (client, _, proposal_repo, _):
        proposal = _proposal()
        proposal.assigned_to = PermissionId("permission-direction")
        await proposal_repo.add(proposal)

        invalid = await client.post(
            "/api/v1/proposals/prop-1/return-to-staff",
            json={"targetPermissionId": "permission-target", "reason": ""},
        )
        response = await client.post(
            "/api/v1/proposals/prop-1/return-to-staff",
            json={
                "targetPermissionId": "permission-target",
                "reason": "Please revise the insurance conditions",
            },
        )

    assert invalid.status_code == 422
    assert response.status_code == 200
    body = response.json()
    assert body["assignedTo"]["permissionId"] == "permission-target"
    assert body["lastEvent"]["type"] == "DIRECTION_CLARIFIED"
    assert body["lastEvent"]["note"] == "Please revise the insurance conditions"
    assert body["lastEvent"]["targetPermission"]["permissionId"] == (
        "permission-target"
    )
    assert notification_dispatcher.calls == [
        {
            "recipient_permission_id": "permission-target",
            "kind": "PROPOSAL_RETURNED_TO_STAFF",
            "triggered_by": "permission-direction",
            "related_resource_type": "PROPOSAL",
            "related_resource_id": "prop-1",
            "related_resource_label": "VRP-20260601-0001",
            "note": "Please revise the insurance conditions",
        }
    ]


async def test_direction_cannot_read_a_proposal_assigned_to_another_member() -> None:
    direction_caller = Actor(
        id=PermissionId("permission-direction"),
        group=GroupName.DIRECTION,
        email="direction@example.org",
    )
    async with client_with_repos(caller=direction_caller) as (
        client,
        _,
        proposal_repo,
        _,
    ):
        proposal = _proposal()
        proposal.assigned_to = PermissionId("another-direction-permission")
        await proposal_repo.add(proposal)

        response = await client.get("/api/v1/proposals/prop-1")

    assert response.status_code == 403
    assert response.json()["error"] == "ACCESS_DENIED"


async def test_proposal_event_log_is_sorted_newest_first_before_pagination() -> None:
    async with client_with_repos() as (client, _, proposal_repo, _):
        proposal = _proposal()
        proposal.events = [
            ProposalEvent(
                occurred_at=datetime(2026, 8, 29, 9, tzinfo=UTC),
                type=ProposalEventType.SUBMITTED,
                triggered_by=PermissionId("permission-1"),
                note="Oldest",
            ),
            ProposalEvent(
                occurred_at=datetime(2026, 8, 31, 11, tzinfo=UTC),
                type=ProposalEventType.FORWARDED,
                triggered_by=PermissionId("permission-1"),
                note="Newest",
            ),
            ProposalEvent(
                occurred_at=datetime(2026, 8, 30, 10, tzinfo=UTC),
                type=ProposalEventType.ASSIGNED,
                triggered_by=PermissionId("permission-1"),
                note="Middle",
            ),
        ]
        await proposal_repo.add(proposal)

        first_page = await client.get(
            "/api/v1/proposals/prop-1/events", params={"page": 0, "size": 2}
        )
        second_page = await client.get(
            "/api/v1/proposals/prop-1/events", params={"page": 1, "size": 2}
        )

    assert first_page.status_code == 200
    assert [event["note"] for event in first_page.json()["content"]] == [
        "Newest",
        "Middle",
    ]
    assert [event["note"] for event in second_page.json()["content"]] == ["Oldest"]


async def test_assign_proposal_to_self_sends_no_notification_or_email() -> None:
    notification_dispatcher = RecordingNotificationDispatcher()
    proposal_email_sender = RecordingProposalNotificationEmailSender()
    async with client_with_repos(
        caller=_STAFF_CALLER,
        permission_records={
            "permission-staff": _permission_record(
                "permission-staff", GroupName.CURATORIAL
            )
        },
        notification_dispatcher=notification_dispatcher,
        proposal_email_sender=proposal_email_sender,
    ) as (client, _, proposal_repo, _):
        await proposal_repo.add(
            Proposal(
                id=ProposalId("prop-1"),
                reference_number=ReferenceNumber("VRP-20260601-0001"),
                title="Proposal title",
                collection_use_project_id=CollectionUseProjectId("proj-1"),
                intended_use=UseType.IN_SITU_VISIT,
                begin_date=date(2026, 6, 1),
                end_date=date(2026, 6, 7),
                status=ProposalStatus.SUBMITTED,
                requested_by=PermissionId("permission-1"),
                submitted_at=datetime(2026, 6, 7, tzinfo=UTC),
                submission_channel=SubmissionChannel.AUTHENTICATED,
            )
        )

        response = await client.post(
            "/api/v1/proposals/prop-1/assign",
            json={},
        )

    assert response.status_code == 200
    assert response.json()["assignedTo"]["permissionId"] == "permission-staff"
    assert notification_dispatcher.calls == []
    assert proposal_email_sender.assigned_calls == []
    assert proposal_email_sender.forwarded_calls == []


async def test_take_over_assignment_notifies_previous_assignee() -> None:
    notification_dispatcher = RecordingNotificationDispatcher()
    proposal_email_sender = RecordingProposalNotificationEmailSender()
    async with client_with_repos(
        caller=_STAFF_CALLER,
        permission_records={
            "permission-staff": _permission_record(
                "permission-staff", GroupName.CURATORIAL
            ),
            "permission-target": _permission_record(
                "permission-target", GroupName.COLLECTIONS_MANAGEMENT
            ),
        },
        notification_dispatcher=notification_dispatcher,
        proposal_email_sender=proposal_email_sender,
    ) as (client, _, proposal_repo, _):
        await proposal_repo.add(
            Proposal(
                id=ProposalId("prop-1"),
                reference_number=ReferenceNumber("VRP-20260601-0001"),
                title="Proposal title",
                collection_use_project_id=CollectionUseProjectId("proj-1"),
                intended_use=UseType.IN_SITU_VISIT,
                begin_date=date(2026, 6, 1),
                end_date=date(2026, 6, 7),
                status=ProposalStatus.PENDING,
                requested_by=PermissionId("permission-1"),
                assigned_to=PermissionId("permission-target"),
                submitted_at=datetime(2026, 6, 7, tzinfo=UTC),
                submission_channel=SubmissionChannel.AUTHENTICATED,
            )
        )

        response = await client.post(
            "/api/v1/proposals/prop-1/assign",
            json={"note": "Taking this over"},
        )

    assert response.status_code == 200
    assert response.json()["assignedTo"]["permissionId"] == "permission-staff"
    assert notification_dispatcher.calls == [
        {
            "recipient_permission_id": "permission-target",
            "kind": "PROPOSAL_TAKEN_OVER",
            "triggered_by": "permission-staff",
            "related_resource_type": "PROPOSAL",
            "related_resource_id": "prop-1",
            "related_resource_label": "VRP-20260601-0001",
            "note": "Taking this over",
        }
    ]
    assert proposal_email_sender.taken_over_calls == [
        {
            "to_email": "permission-target@example.org",
            "recipient_name": "User permission-target",
            "proposal_reference": "VRP-20260601-0001",
            "taken_over_by_name": "User permission-staff",
            "note": "Taking this over",
            "link": f"{settings.public_origin}/p/collections/proposals/prop-1",
        }
    ]
    assert proposal_email_sender.assigned_calls == []


async def test_forward_proposal_to_self_sends_no_notification_or_email() -> None:
    notification_dispatcher = RecordingNotificationDispatcher()
    proposal_email_sender = RecordingProposalNotificationEmailSender()
    async with client_with_repos(
        caller=_STAFF_CALLER,
        permission_records={
            "permission-staff": _permission_record(
                "permission-staff", GroupName.CURATORIAL
            )
        },
        notification_dispatcher=notification_dispatcher,
        proposal_email_sender=proposal_email_sender,
    ) as (client, _, proposal_repo, _):
        await proposal_repo.add(
            Proposal(
                id=ProposalId("prop-1"),
                reference_number=ReferenceNumber("VRP-20260601-0001"),
                title="Proposal title",
                collection_use_project_id=CollectionUseProjectId("proj-1"),
                intended_use=UseType.IN_SITU_VISIT,
                begin_date=date(2026, 6, 1),
                end_date=date(2026, 6, 7),
                status=ProposalStatus.PENDING,
                requested_by=PermissionId("permission-1"),
                assigned_to=PermissionId("permission-target"),
                submitted_at=datetime(2026, 6, 7, tzinfo=UTC),
                submission_channel=SubmissionChannel.AUTHENTICATED,
            )
        )

        response = await client.post(
            "/api/v1/proposals/prop-1/forward",
            json={"targetPermissionId": "permission-staff"},
        )

    assert response.status_code == 200
    assert response.json()["assignedTo"]["permissionId"] == "permission-staff"
    assert notification_dispatcher.calls == []
    assert proposal_email_sender.assigned_calls == []
    assert proposal_email_sender.forwarded_calls == []


async def test_forward_proposal_rejects_non_pending_proposal() -> None:
    async with client_with_repos(
        caller=_STAFF_CALLER,
        permission_records={
                "permission-target": _permission_record(
                    "permission-target", GroupName.COLLECTIONS_MANAGEMENT
                )
        },
    ) as (client, _, proposal_repo, _):
        await proposal_repo.add(
            Proposal(
                id=ProposalId("prop-1"),
                reference_number=ReferenceNumber("VRP-20260601-0001"),
                title="Proposal title",
                collection_use_project_id=CollectionUseProjectId("proj-1"),
                intended_use=UseType.IN_SITU_VISIT,
                begin_date=date(2026, 6, 1),
                end_date=date(2026, 6, 7),
                status=ProposalStatus.APPROVED,
                requested_by=PermissionId("permission-1"),
                submitted_at=datetime(2026, 6, 7, tzinfo=UTC),
                submission_channel=SubmissionChannel.AUTHENTICATED,
            )
        )

        response = await client.post(
            "/api/v1/proposals/prop-1/forward",
            json={"targetPermissionId": "permission-target"},
        )
        proposal = await proposal_repo.get_by_id(ProposalId("prop-1"))

    assert response.status_code == 409
    assert response.json()["error"] == "INVALID_TRANSITION"
    assert proposal is not None
    assert proposal.assigned_to is None


async def test_staff_can_patch_proposal_title() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        _,
        proposal_repo,
        _,
    ):
        await proposal_repo.add(_proposal())

        response = await client.patch(
            "/api/v1/proposals/prop-1",
            json={"title": "Corrected title"},
        )
        proposal = await proposal_repo.get_by_id(ProposalId("prop-1"))

    assert response.status_code == 200
    assert response.json()["title"] == "Corrected title"
    assert proposal is not None
    assert proposal.title == "Corrected title"


async def test_patch_proposal_null_title_clears_it() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        _,
        proposal_repo,
        _,
    ):
        await proposal_repo.add(_proposal())

        response = await client.patch(
            "/api/v1/proposals/prop-1",
            json={"title": None},
        )
        proposal = await proposal_repo.get_by_id(ProposalId("prop-1"))

    assert response.status_code == 200
    assert response.json()["title"] is None
    assert proposal is not None
    assert proposal.title is None


async def test_patch_proposal_omitted_fields_left_unchanged() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        _,
        proposal_repo,
        _,
    ):
        await proposal_repo.add(_proposal())

        response = await client.patch(
            "/api/v1/proposals/prop-1",
            json={"title": "Only the title"},
        )
        proposal = await proposal_repo.get_by_id(ProposalId("prop-1"))

    assert response.status_code == 200
    assert proposal is not None
    # Dates and intended use untouched by a title-only patch.
    assert proposal.begin_date == date(2026, 6, 1)
    assert proposal.end_date == date(2026, 6, 7)
    assert proposal.intended_use == UseType.IN_SITU_VISIT


async def test_patch_proposal_replaces_intended_use() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        _,
        proposal_repo,
        _,
    ):
        await proposal_repo.add(_proposal())

        response = await client.patch(
            "/api/v1/proposals/prop-1",
            json={"intendedUse": "IN_SITU_VISIT"},
        )
        proposal = await proposal_repo.get_by_id(ProposalId("prop-1"))

    assert response.status_code == 200
    assert proposal is not None
    assert proposal.intended_use == UseType.IN_SITU_VISIT


async def test_patch_proposal_clears_dates() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        _,
        proposal_repo,
        _,
    ):
        await proposal_repo.add(_proposal())

        response = await client.patch(
            "/api/v1/proposals/prop-1",
            json={"beginDate": None, "endDate": None},
        )
        proposal = await proposal_repo.get_by_id(ProposalId("prop-1"))

    assert response.status_code == 200
    body = response.json()
    assert body["beginDate"] is None
    assert body["endDate"] is None
    assert proposal is not None
    assert proposal.begin_date is None
    assert proposal.end_date is None


async def test_external_owner_cannot_patch_proposal() -> None:
    async with client_with_repos() as (client, _, proposal_repo, _):
        await proposal_repo.add(_proposal())

        response = await client.patch(
            "/api/v1/proposals/prop-1",
            json={"title": "Hijacked"},
            headers={"X-Permission-Id": "permission-1"},
        )
        proposal = await proposal_repo.get_by_id(ProposalId("prop-1"))

    assert response.status_code == 403
    assert response.json()["error"] == "INSUFFICIENT_GROUP"
    assert proposal is not None
    assert proposal.title == "Proposal title"


async def test_patch_proposal_terminal_status_returns_409() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        _,
        proposal_repo,
        _,
    ):
        await proposal_repo.add(_proposal(status=ProposalStatus.APPROVED))

        response = await client.patch(
            "/api/v1/proposals/prop-1",
            json={"title": "Too late"},
        )
        proposal = await proposal_repo.get_by_id(ProposalId("prop-1"))

    assert response.status_code == 409
    assert response.json()["error"] == "INVALID_TRANSITION"
    assert proposal is not None
    assert proposal.title == "Proposal title"


async def test_patch_proposal_invalid_date_range_returns_422() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        _,
        proposal_repo,
        _,
    ):
        # Stored begin is 2026-06-01; patching only the end to an earlier date
        # must be rejected against the effective (stored + incoming) range.
        await proposal_repo.add(_proposal())

        response = await client.patch(
            "/api/v1/proposals/prop-1",
            json={"endDate": "2026-05-01"},
        )
        proposal = await proposal_repo.get_by_id(ProposalId("prop-1"))

    assert response.status_code == 422
    assert response.json()["error"] == "INVALID_DATE_RANGE"
    assert proposal is not None
    assert proposal.end_date == date(2026, 6, 7)


async def test_patch_proposal_unknown_id_returns_404() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (client, _, _, _):
        response = await client.patch(
            "/api/v1/proposals/missing",
            json={"title": "x"},
        )

    assert response.status_code == 404
    assert response.json()["error"] == "PROPOSAL_NOT_FOUND"


async def test_staff_can_patch_project_details() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        project_repo,
        proposal_repo,
        _,
    ):
        await project_repo.add(_project())
        await proposal_repo.add(_proposal())

        response = await client.patch(
            "/api/v1/collection-use-projects/proj-1",
            json={
                "title": "Corrected project",
                "purpose": "Corrected purpose",
                "beginDate": "2026-07-01",
                "endDate": "2026-07-05",
            },
        )
        project = await project_repo.get_by_id(CollectionUseProjectId("proj-1"))

    assert response.status_code == 200
    assert response.json()["title"] == "Corrected project"
    assert response.json()["purpose"] == "Corrected purpose"
    assert response.json()["beginDate"] == "2026-07-01"
    assert response.json()["endDate"] == "2026-07-05"
    assert project is not None
    assert project.title == "Corrected project"
    assert project.purpose == "Corrected purpose"
    assert project.begin_date == date(2026, 7, 1)
    assert project.end_date == date(2026, 7, 5)


async def test_patch_project_requires_staff() -> None:
    async with client_with_repos(caller=_CALLER) as (
        client,
        project_repo,
        proposal_repo,
        _,
    ):
        await project_repo.add(_project())
        await proposal_repo.add(_proposal())

        response = await client.patch(
            "/api/v1/collection-use-projects/proj-1",
            json={"title": "Requester correction"},
        )
        project = await project_repo.get_by_id(CollectionUseProjectId("proj-1"))

    assert response.status_code == 403
    assert response.json()["error"] == "INSUFFICIENT_GROUP"
    assert project is not None
    assert project.title == "Project title"


async def test_patch_project_invalid_date_range_returns_422() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        project_repo,
        proposal_repo,
        _,
    ):
        await project_repo.add(_project())
        await proposal_repo.add(_proposal())

        response = await client.patch(
            "/api/v1/collection-use-projects/proj-1",
            json={"endDate": "2026-05-01"},
        )
        project = await project_repo.get_by_id(CollectionUseProjectId("proj-1"))

    assert response.status_code == 422
    assert response.json()["error"] == "INVALID_DATE_RANGE"
    assert project is not None
    assert project.end_date == date(2026, 6, 7)


async def test_patch_project_terminal_status_returns_409() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        project_repo,
        proposal_repo,
        _,
    ):
        await project_repo.add(_project(status=UseStatus.COMPLETED))
        await proposal_repo.add(_proposal())

        response = await client.patch(
            "/api/v1/collection-use-projects/proj-1",
            json={"title": "Too late"},
        )
        project = await project_repo.get_by_id(CollectionUseProjectId("proj-1"))

    assert response.status_code == 409
    assert response.json()["error"] == "INVALID_TRANSITION"
    assert project is not None
    assert project.title == "Project title"


async def test_complete_project_without_objects_returns_409() -> None:
    async with client_with_repos(caller=_CALLER) as (
        client,
        project_repo,
        proposal_repo,
        _,
    ):
        await project_repo.add(_project(status=UseStatus.IN_PROGRESS, objects=[]))
        await proposal_repo.add(_proposal())

        response = await client.post(
            "/api/v1/collection-use-projects/proj-1/complete",
            json={"note": "Done without objects."},
        )
        project = await project_repo.get_by_id(CollectionUseProjectId("proj-1"))

    assert response.status_code == 409
    assert response.json()["error"] == "INVALID_TRANSITION"
    assert "at least one object" in response.json()["message"]
    assert project is not None
    assert project.status == UseStatus.IN_PROGRESS


async def test_start_project_notifies_external_requester() -> None:
    proposal_email_sender = RecordingProposalNotificationEmailSender()
    async with client_with_repos(
        caller=_STAFF_CALLER,
        permission_records={
            "permission-1": _permission_record(
                "permission-1",
                GroupName.EXTERNAL,
                user_name="Alice Requester",
                user_email="alice@example.org",
            ),
            "permission-staff": _permission_record(
                "permission-staff",
                GroupName.CURATORIAL,
                user_name="Curator One",
                user_email="curator@example.org",
            ),
        },
        proposal_email_sender=proposal_email_sender,
    ) as (client, project_repo, proposal_repo, _):
        await project_repo.add(
            _project(status=UseStatus.CREATED, objects=[_collection_use_object()])
        )
        await proposal_repo.add(_proposal(status=ProposalStatus.APPROVED))

        response = await client.post(
            "/api/v1/collection-use-projects/proj-1/start",
            json={"note": "Starting work."},
        )

    assert response.status_code == 200
    assert proposal_email_sender.project_started_calls == [
        {
            "to_email": "alice@example.org",
            "requester_name": "Alice Requester",
            "project_reference": "CUP-ABCDEFG1",
            "started_by_name": "Curator One",
            "link": f"{settings.public_origin}/p/collections/projects/proj-1",
        }
    ]


async def test_cancel_project_notifies_external_requester() -> None:
    proposal_email_sender = RecordingProposalNotificationEmailSender()
    async with client_with_repos(
        caller=_STAFF_CALLER,
        permission_records={
            "permission-1": _permission_record(
                "permission-1",
                GroupName.EXTERNAL,
                user_name="Alice Requester",
                user_email="alice@example.org",
            ),
            "permission-staff": _permission_record(
                "permission-staff",
                GroupName.CURATORIAL,
                user_name="Curator One",
                user_email="curator@example.org",
            ),
        },
        proposal_email_sender=proposal_email_sender,
    ) as (client, project_repo, proposal_repo, _):
        await project_repo.add(
            _project(status=UseStatus.IN_PROGRESS, objects=[_collection_use_object()])
        )
        await proposal_repo.add(_proposal(status=ProposalStatus.APPROVED))

        response = await client.post(
            "/api/v1/collection-use-projects/proj-1/cancel",
            json={"reason": "Loan no longer possible."},
        )

    assert response.status_code == 200
    assert proposal_email_sender.project_cancelled_calls == [
        {
            "to_email": "alice@example.org",
            "requester_name": "Alice Requester",
            "project_reference": "CUP-ABCDEFG1",
            "cancelled_by_name": "Curator One",
            "reason": "Loan no longer possible.",
            "link": f"{settings.public_origin}/p/collections/projects/proj-1",
        }
    ]


async def test_complete_project_notifies_external_requester() -> None:
    proposal_email_sender = RecordingProposalNotificationEmailSender()
    async with client_with_repos(
        caller=_STAFF_CALLER,
        permission_records={
            "permission-1": _permission_record(
                "permission-1",
                GroupName.EXTERNAL,
                user_name="Alice Requester",
                user_email="alice@example.org",
            ),
            "permission-staff": _permission_record(
                "permission-staff",
                GroupName.CURATORIAL,
                user_name="Curator One",
                user_email="curator@example.org",
            ),
        },
        proposal_email_sender=proposal_email_sender,
    ) as (client, project_repo, proposal_repo, _):
        await project_repo.add(
            _project(status=UseStatus.IN_PROGRESS, objects=[_collection_use_object()])
        )
        await proposal_repo.add(_proposal(status=ProposalStatus.APPROVED))

        response = await client.post(
            "/api/v1/collection-use-projects/proj-1/complete",
            json={"note": "Research completed."},
        )

    assert response.status_code == 200
    assert proposal_email_sender.project_completed_calls == [
        {
            "to_email": "alice@example.org",
            "requester_name": "Alice Requester",
            "project_reference": "CUP-ABCDEFG1",
            "completed_by_name": "Curator One",
            "link": f"{settings.public_origin}/p/collections/projects/proj-1",
        }
    ]


async def test_staff_can_add_project_objects() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        project_repo,
        proposal_repo,
        _,
    ):
        await project_repo.add(_project())
        await proposal_repo.add(_proposal())

        response = await client.post(
            "/api/v1/collection-use-projects/proj-1/objects",
            json={
                "objects": [
                    {
                        "inventoryNumber": "INV-002",
                        "displayTitle": "Specimen drawer",
                        "objectName": "Drawer",
                        "briefDescriptionSnapshot": "A drawer with specimens.",
                        "collectionId": "collection-zoology",
                        "collectionName": "Zoology",
                        "category": "zoology",
                        "description": "Selected from object index.",
                    }
                ]
            },
        )
        project = await project_repo.get_by_id(CollectionUseProjectId("proj-1"))

    assert response.status_code == 201
    assert response.json()["objects"][-1]["inventoryNumber"] == "INV-002"
    assert response.json()["objects"][-1]["collectionId"] == "collection-zoology"
    assert response.json()["objects"][-1]["collectionName"] == "Zoology"
    assert project is not None
    assert project.objects[-1].inventory_number == "INV-002"
    assert project.objects[-1].display_title == "Specimen drawer"
    assert project.objects[-1].collection_id == "collection-zoology"
    assert project.objects[-1].collection_name == "Zoology"
    assert project.objects[-1].requested_by == _STAFF_CALLER.id


async def test_staff_can_create_follow_up_project() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        project_repo,
        proposal_repo,
        _,
    ):
        await project_repo.add(
            _project(
                status=UseStatus.COMPLETED,
                objects=[
                    _collection_use_object("cuo-1", "INV-001"),
                    _collection_use_object("cuo-2", "INV-002"),
                ],
            )
        )
        await proposal_repo.add(_proposal())

        response = await client.post(
            "/api/v1/collection-use-projects/proj-1/follow-ups",
            json={
                "beginDate": "2026-08-10",
                "endDate": "2026-08-20",
                "objectIds": ["cuo-2"],
                "title": "Follow-up title",
                "purpose": "Continue the study",
                "note": "Second campaign.",
            },
        )

    body = response.json()
    assert response.status_code == 201
    assert body["id"] != "proj-1"
    assert body["referenceNumber"] == "CUP-00000001"
    assert body["status"] == "CREATED"
    assert body["originProjectId"] == "proj-1"
    assert body["proposal"] is None
    assert [obj["inventoryNumber"] for obj in body["objects"]] == ["INV-002"]


async def test_follow_up_project_requires_staff() -> None:
    async with client_with_repos(caller=_CALLER) as (
        client,
        project_repo,
        proposal_repo,
        _,
    ):
        await project_repo.add(
            _project(status=UseStatus.COMPLETED, objects=[_collection_use_object()])
        )
        await proposal_repo.add(_proposal())

        response = await client.post(
            "/api/v1/collection-use-projects/proj-1/follow-ups",
            json={
                "beginDate": "2026-08-10",
                "endDate": "2026-08-20",
                "objectIds": ["cuo-1"],
            },
        )

    assert response.status_code == 403
    assert response.json()["error"] == "INSUFFICIENT_GROUP"


async def test_follow_up_project_rejects_non_completed_origin() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        project_repo,
        proposal_repo,
        _,
    ):
        await project_repo.add(
            _project(status=UseStatus.IN_PROGRESS, objects=[_collection_use_object()])
        )
        await proposal_repo.add(_proposal())

        response = await client.post(
            "/api/v1/collection-use-projects/proj-1/follow-ups",
            json={
                "beginDate": "2026-08-10",
                "endDate": "2026-08-20",
                "objectIds": ["cuo-1"],
            },
        )

    assert response.status_code == 409
    assert response.json()["error"] == "INVALID_TRANSITION"


async def test_follow_up_project_rejects_missing_origin() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (client, _, _, _):
        response = await client.post(
            "/api/v1/collection-use-projects/missing-project/follow-ups",
            json={
                "beginDate": "2026-08-10",
                "endDate": "2026-08-20",
                "objectIds": ["cuo-1"],
            },
        )

    assert response.status_code == 404
    assert response.json()["error"] == "PROJECT_NOT_FOUND"


async def test_follow_up_project_rejects_empty_object_ids() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        project_repo,
        proposal_repo,
        _,
    ):
        await project_repo.add(
            _project(status=UseStatus.COMPLETED, objects=[_collection_use_object()])
        )
        await proposal_repo.add(_proposal())

        response = await client.post(
            "/api/v1/collection-use-projects/proj-1/follow-ups",
            json={"beginDate": "2026-08-10", "endDate": "2026-08-20", "objectIds": []},
        )

    assert response.status_code == 422
    assert response.json()["error"] == "VALIDATION_ERROR"


async def test_follow_up_project_rejects_invalid_date_range() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        project_repo,
        proposal_repo,
        _,
    ):
        await project_repo.add(
            _project(status=UseStatus.COMPLETED, objects=[_collection_use_object()])
        )
        await proposal_repo.add(_proposal())

        response = await client.post(
            "/api/v1/collection-use-projects/proj-1/follow-ups",
            json={
                "beginDate": "2026-08-20",
                "endDate": "2026-08-10",
                "objectIds": ["cuo-1"],
            },
        )

    assert response.status_code == 422
    assert response.json()["error"] == "VALIDATION_ERROR"


async def test_follow_up_project_does_not_copy_journal_logs() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        project_repo,
        proposal_repo,
        _,
    ):
        await project_repo.add(
            _project(status=UseStatus.COMPLETED, objects=[_collection_use_object()])
        )
        await proposal_repo.add(_proposal())

        response = await client.post(
            "/api/v1/collection-use-projects/proj-1/follow-ups",
            json={
                "beginDate": "2026-08-10",
                "endDate": "2026-08-20",
                "objectIds": ["cuo-1"],
            },
        )
        new_project_id = response.json()["id"]

        access_log = await client.get(
            f"/api/v1/collection-use-projects/{new_project_id}/object-access-log"
        )
        occurrence_log = await client.get(
            f"/api/v1/collection-use-projects/{new_project_id}/object-occurrence-log"
        )
        publication_log = await client.get(
            f"/api/v1/collection-use-projects/{new_project_id}/publication-log"
        )

    assert response.status_code == 201
    assert access_log.status_code == 404
    assert occurrence_log.status_code == 404
    assert publication_log.status_code == 404


async def test_follow_up_project_owner_can_access_created_follow_up_project() -> None:
    """Regression test: `requestedBy` is copied from the origin project onto
    the follow-up, so that same (non-staff) requester must be able to load
    the follow-up's own detail afterwards — not just see it listed under
    "my projects". This used to 403 because project-level access checks
    resolved ownership solely through a linked `Proposal`, and a follow-up
    project has none (see `assert_project_access`)."""
    project_repo = InMemoryProjectRepository()
    proposal_repo = InMemoryProposalRepository()
    session = CommitOnlySession(None)
    caller_holder: dict[str, Actor] = {"actor": _STAFF_CALLER}

    app.dependency_overrides[get_project_repo] = lambda: project_repo
    app.dependency_overrides[get_proposal_repo] = lambda: proposal_repo
    app.dependency_overrides[get_conversation_repo] = lambda: (
        InMemoryConversationRepository()
    )
    app.dependency_overrides[get_access_log_repo] = lambda: (
        InMemoryAccessLogRepository()
    )
    app.dependency_overrides[get_occurrence_log_repo] = lambda: (
        InMemoryOccurrenceLogRepository()
    )
    app.dependency_overrides[get_publication_log_repo] = lambda: (
        InMemoryPublicationLogRepository()
    )
    app.dependency_overrides[get_file_storage] = lambda: InMemoryFileStorage()
    app.dependency_overrides[get_async_session] = lambda: session
    app.dependency_overrides[get_caller_permission] = lambda: caller_holder["actor"]
    app.dependency_overrides[get_external_requester_provisioner] = lambda: (
        RecordingRequesterProvisioner()
    )
    app.dependency_overrides[get_requester_access_email_sender] = lambda: (
        RecordingAccessEmailSender()
    )
    app.dependency_overrides[get_reference_number_generator] = lambda: (
        InMemoryReferenceNumberGenerator(proposal_repo)
    )

    try:
        await project_repo.add(
            _project(status=UseStatus.COMPLETED, objects=[_collection_use_object()])
        )
        await proposal_repo.add(_proposal())

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            create_response = await client.post(
                "/api/v1/collection-use-projects/proj-1/follow-ups",
                json={
                    "beginDate": "2026-08-10",
                    "endDate": "2026-08-20",
                    "objectIds": ["cuo-1"],
                },
            )
            assert create_response.status_code == 201
            new_project_id = create_response.json()["id"]

            # The origin project's own (non-staff) requester is `_CALLER`
            # (see `_project`'s default `requested_by`), and it is copied
            # onto the follow-up unchanged.
            caller_holder["actor"] = _CALLER

            detail_response = await client.get(
                f"/api/v1/collection-use-projects/{new_project_id}"
            )
            list_response = await client.get(
                "/api/v1/collection-use-projects",
                params={"requestedBy": _CALLER.id},
            )
    finally:
        app.dependency_overrides.clear()

    assert detail_response.status_code == 200
    assert detail_response.json()["id"] == new_project_id
    assert new_project_id in [item["id"] for item in list_response.json()["content"]]


async def test_add_project_objects_requires_staff() -> None:
    async with client_with_repos(caller=_CALLER) as (
        client,
        project_repo,
        proposal_repo,
        _,
    ):
        await project_repo.add(_project())
        await proposal_repo.add(_proposal())

        response = await client.post(
            "/api/v1/collection-use-projects/proj-1/objects",
            json={
                "objects": [
                    {
                        "inventoryNumber": "INV-002",
                        "displayTitle": "Specimen drawer",
                        "objectName": "Drawer",
                    }
                ]
            },
        )
        project = await project_repo.get_by_id(CollectionUseProjectId("proj-1"))

    assert response.status_code == 403
    assert response.json()["error"] == "INSUFFICIENT_GROUP"
    assert project is not None
    assert project.objects == []


async def test_add_project_objects_terminal_status_returns_409() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        project_repo,
        proposal_repo,
        _,
    ):
        await project_repo.add(_project(status=UseStatus.COMPLETED))
        await proposal_repo.add(_proposal())

        response = await client.post(
            "/api/v1/collection-use-projects/proj-1/objects",
            json={
                "objects": [
                    {
                        "inventoryNumber": "INV-002",
                        "displayTitle": "Specimen drawer",
                        "objectName": "Drawer",
                    }
                ]
            },
        )

    assert response.status_code == 409
    assert response.json()["error"] == "INVALID_TRANSITION"


async def test_add_project_objects_syncs_new_objects_to_existing_access_log() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        project_repo,
        proposal_repo,
        _,
    ):
        await project_repo.add(
            _project(status=UseStatus.IN_PROGRESS, objects=[_collection_use_object()])
        )
        await proposal_repo.add(_proposal())
        access_log_repo = app.dependency_overrides[get_access_log_repo]()
        access_log = ObjectAccessLog(
            id=ObjectAccessLogId("log-1"),
            reference_number=ReferenceNumber("OAL-ABCDEFG1"),
            collection_use_project_id=CollectionUseProjectId("proj-1"),
        )
        await access_log_repo.add(access_log)
        await access_log_repo.save_entry(
            ObjectLogEntry(
                id=ObjectLogEntryId("entry-1"),
                object_access_log_id=ObjectAccessLogId("log-1"),
                collection_use_object_id=CollectionUseObjectId("cuo-1"),
                number_of_objects=1,
                added_at=datetime(2026, 6, 2, tzinfo=UTC),
                added_by=PermissionId("permission-staff"),
            )
        )

        added = await client.post(
            "/api/v1/collection-use-projects/proj-1/objects",
            json={
                "objects": [
                    {
                        "inventoryNumber": "INV-002",
                        "displayTitle": "Specimen drawer",
                        "objectName": "Drawer",
                    },
                    {
                        "inventoryNumber": "INV-003",
                        "displayTitle": "Field notebook",
                        "objectName": "Notebook",
                    },
                ]
            },
        )
        new_ids = [obj["id"] for obj in added.json()["objects"][-2:]]
        listing = await client.get("/api/v1/collection-use-projects/proj-1/log-entries")

    assert added.status_code == 201
    assert listing.status_code == 200
    entries = listing.json()["content"]
    synced = [entry for entry in entries if entry["collectionUseObjectId"] in new_ids]
    assert len(synced) == 2
    assert {entry["numberOfObjects"] for entry in synced} == {1}
    assert {entry["addedBy"]["permissionId"] for entry in synced} == {
        "permission-staff"
    }
    assert sum(entry["collectionUseObjectId"] == "cuo-1" for entry in entries) == 1


async def test_add_project_objects_creates_access_log_when_missing() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        project_repo,
        proposal_repo,
        _,
    ):
        await project_repo.add(_project())
        await proposal_repo.add(_proposal())

        added = await client.post(
            "/api/v1/collection-use-projects/proj-1/objects",
            json={
                "objects": [
                    {
                        "inventoryNumber": "INV-002",
                        "displayTitle": "Specimen drawer",
                        "objectName": "Drawer",
                    }
                ]
            },
        )
        listing = await client.get("/api/v1/collection-use-projects/proj-1/log-entries")

    assert added.status_code == 201
    assert listing.status_code == 200
    assert listing.json()["accessLog"]["referenceNumber"].startswith("OAL-")
    assert len(listing.json()["content"]) == 1
    assert (
        listing.json()["content"][0]["collectionUseObjectId"]
        == (added.json()["objects"][-1]["id"])
    )
    assert listing.json()["content"][0]["numberOfObjects"] == 1


async def test_add_project_objects_blocks_when_access_log_concluded() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        project_repo,
        proposal_repo,
        _,
    ):
        await project_repo.add(_project(status=UseStatus.IN_PROGRESS))
        await proposal_repo.add(_proposal())
        access_log_repo = app.dependency_overrides[get_access_log_repo]()
        await access_log_repo.add(
            ObjectAccessLog(
                id=ObjectAccessLogId("log-1"),
                reference_number=ReferenceNumber("OAL-ABCDEFG1"),
                collection_use_project_id=CollectionUseProjectId("proj-1"),
                date_conclusion=datetime(2026, 6, 3, tzinfo=UTC),
            )
        )

        response = await client.post(
            "/api/v1/collection-use-projects/proj-1/objects",
            json={
                "objects": [
                    {
                        "inventoryNumber": "INV-002",
                        "displayTitle": "Specimen drawer",
                        "objectName": "Drawer",
                    }
                ]
            },
        )
        project = await project_repo.get_by_id(CollectionUseProjectId("proj-1"))

    assert response.status_code == 409
    assert response.json()["error"] == "INVALID_TRANSITION"
    assert project is not None
    assert project.objects == []


async def test_staff_can_remove_unused_project_object() -> None:
    project_object = _collection_use_object()
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        project_repo,
        proposal_repo,
        _,
    ):
        await project_repo.add(_project(objects=[project_object]))
        await proposal_repo.add(_proposal())

        response = await client.delete(
            "/api/v1/collection-use-projects/proj-1/objects/cuo-1",
        )
        project = await project_repo.get_by_id(CollectionUseProjectId("proj-1"))

    assert response.status_code == 204
    assert project is not None
    assert project.objects == []


async def test_remove_project_object_removes_automatic_log_entry() -> None:
    project_object = _collection_use_object()
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        project_repo,
        proposal_repo,
        _,
    ):
        await project_repo.add(_project(objects=[project_object]))
        await proposal_repo.add(_proposal())
        access_log_repo = app.dependency_overrides[get_access_log_repo]()
        access_log = ObjectAccessLog(
            id=ObjectAccessLogId("log-1"),
            reference_number=ReferenceNumber("OAL-ABCDEFG1"),
            collection_use_project_id=CollectionUseProjectId("proj-1"),
        )
        await access_log_repo.add(access_log)
        await access_log_repo.save_entry(
            ObjectLogEntry(
                id=ObjectLogEntryId("entry-1"),
                object_access_log_id=ObjectAccessLogId("log-1"),
                collection_use_object_id=CollectionUseObjectId("cuo-1"),
                number_of_objects=1,
                added_at=datetime(2026, 6, 2, tzinfo=UTC),
                added_by=PermissionId("permission-staff"),
            )
        )

        response = await client.delete(
            "/api/v1/collection-use-projects/proj-1/objects/cuo-1",
        )
        project = await project_repo.get_by_id(CollectionUseProjectId("proj-1"))
        entries, total = await access_log_repo.list_entries_by_project(
            CollectionUseProjectId("proj-1"), None, 0, 10
        )

    assert response.status_code == 204
    assert project is not None
    assert project.objects == []
    assert total == 0
    assert entries == []


async def test_remove_project_object_blocks_with_dependencies() -> None:
    project_object = _collection_use_object()
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        project_repo,
        proposal_repo,
        _,
    ):
        await project_repo.add(_project(objects=[project_object]))
        await proposal_repo.add(_proposal())
        occurrence_log_repo = app.dependency_overrides[get_occurrence_log_repo]()
        occurrence_log = ObjectOccurrenceLog(
            id=ObjectOccurrenceLogId("occ-log-1"),
            reference_number=ReferenceNumber("OOL-ABCDEFG1"),
            collection_use_project_id=CollectionUseProjectId("proj-1"),
        )
        await occurrence_log_repo.add(occurrence_log)
        await occurrence_log_repo.save_entry(
            ObjectOccurrenceEntry(
                id=ObjectOccurrenceEntryId("occ-entry-1"),
                object_occurrence_log_id=ObjectOccurrenceLogId("occ-log-1"),
                collection_use_object_id=CollectionUseObjectId("cuo-1"),
                number_of_objects=1,
                occurrence_date=datetime(2026, 6, 2, tzinfo=UTC),
                location="Gallery",
                reported_by=PermissionId("permission-staff"),
                detailed_description="Object observed during use.",
            )
        )

        response = await client.delete(
            "/api/v1/collection-use-projects/proj-1/objects/cuo-1",
        )
        project = await project_repo.get_by_id(CollectionUseProjectId("proj-1"))

    assert response.status_code == 409
    assert response.json()["error"] == "PROJECT_OBJECT_HAS_DEPENDENCIES"
    assert response.json()["dependencies"]["occurrenceEntries"] == 1
    assert project is not None
    assert len(project.objects) == 1


async def test_remove_project_object_cascade_requires_confirmation() -> None:
    project_object = _collection_use_object()
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        project_repo,
        proposal_repo,
        _,
    ):
        await project_repo.add(_project(objects=[project_object]))
        await proposal_repo.add(_proposal())

        response = await client.post(
            "/api/v1/collection-use-projects/proj-1/objects/cuo-1/remove",
            json={"confirmCascade": False, "reason": "Wrong object."},
        )

    assert response.status_code == 422
    assert response.json()["error"] == "VALIDATION_ERROR"


async def test_remove_project_object_cascade_removes_dependencies() -> None:
    project_object = _collection_use_object()
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        project_repo,
        proposal_repo,
        _,
    ):
        await project_repo.add(_project(objects=[project_object]))
        await proposal_repo.add(_proposal())
        publication_log_repo = app.dependency_overrides[get_publication_log_repo]()
        publication_log = PublicationLog(
            id=PublicationLogId("pub-log-1"),
            reference_number=ReferenceNumber("PUB-ABCDEFG1"),
            collection_use_project_id=CollectionUseProjectId("proj-1"),
        )
        await publication_log_repo.add(publication_log)
        await publication_log_repo.save_entry(
            PublicationLogEntry(
                id=PublicationLogEntryId("pub-entry-1"),
                publication_log_id=PublicationLogId("pub-log-1"),
                added_at=datetime(2026, 6, 2, tzinfo=UTC),
                added_by=PermissionId("permission-staff"),
                note="Publication mentions this object.",
                collection_use_object_id=CollectionUseObjectId("cuo-1"),
            )
        )

        response = await client.post(
            "/api/v1/collection-use-projects/proj-1/objects/cuo-1/remove",
            json={"confirmCascade": True, "reason": "Wrong object."},
        )
        project = await project_repo.get_by_id(CollectionUseProjectId("proj-1"))
        publication_entries, total = await publication_log_repo.list_entries_by_project(
            CollectionUseProjectId("proj-1"), None, 0, 10
        )

    assert response.status_code == 204
    assert project is not None
    assert project.objects == []
    assert total == 0
    assert publication_entries == []


async def test_approve_proposal_invalid_date_range_returns_422() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        _,
        proposal_repo,
        _,
    ):
        await proposal_repo.add(
            Proposal(
                id=ProposalId("prop-1"),
                reference_number=ReferenceNumber("VRP-20260601-0001"),
                title="Proposal title",
                collection_use_project_id=CollectionUseProjectId("proj-1"),
                intended_use=UseType.IN_SITU_VISIT,
                begin_date=date(2026, 6, 1),
                end_date=date(2026, 6, 7),
                status=ProposalStatus.PENDING,
                requested_by=PermissionId("permission-1"),
                submitted_at=datetime(2026, 6, 7, tzinfo=UTC),
                submission_channel=SubmissionChannel.AUTHENTICATED,
            )
        )

        response = await client.post(
            "/api/v1/proposals/prop-1/approve",
            json={
                "title": "Approved project",
                "purpose": "Use the collection",
                "beginDate": "2026-06-07",
                "endDate": "2026-06-01",
            },
        )

    assert response.status_code == 422
    assert response.json()["error"] == "INVALID_DATE_RANGE"
    assert response.json()["message"] == "endDate must be after beginDate"


async def test_approve_proposal_without_objects_creates_empty_project() -> None:
    proposal_email_sender = RecordingProposalNotificationEmailSender()
    async with client_with_repos(
        caller=_STAFF_CALLER,
        permission_records={
            "permission-1": _permission_record(
                "permission-1",
                GroupName.EXTERNAL,
                user_name="Alice Requester",
                user_email="alice@example.org",
            ),
            "permission-staff": _permission_record(
                "permission-staff",
                GroupName.CURATORIAL,
                user_name="Curator One",
                user_email="curator@example.org",
            ),
        },
        proposal_email_sender=proposal_email_sender,
    ) as (
        client,
        project_repo,
        proposal_repo,
        _,
    ):
        await proposal_repo.add(
            Proposal(
                id=ProposalId("prop-1"),
                reference_number=ReferenceNumber("VRP-20260601-0001"),
                title="Proposal title",
                collection_use_project_id=None,
                intended_use=UseType.IN_SITU_VISIT,
                begin_date=date(2026, 6, 1),
                end_date=date(2026, 6, 7),
                status=ProposalStatus.PENDING,
                requested_by=PermissionId("permission-1"),
                submitted_at=datetime(2026, 6, 7, tzinfo=UTC),
                submission_channel=SubmissionChannel.AUTHENTICATED,
            )
        )

        response = await client.post(
            "/api/v1/proposals/prop-1/approve",
            json={
                "title": "Approved project",
                "purpose": "Use the collection",
                "beginDate": "2026-06-07",
                "endDate": "2026-06-30",
            },
        )
        project_id = response.json()["collectionUseProject"]["id"]
        detail = await client.get(f"/api/v1/collection-use-projects/{project_id}")
        project = await project_repo.get_by_id(CollectionUseProjectId(project_id))

    assert response.status_code == 200
    assert response.json()["collectionUseProject"]["status"] == "CREATED"
    assert detail.status_code == 200
    assert detail.json()["objects"] == []
    assert project is not None
    assert project.objects == []
    assert proposal_email_sender.approved_calls == [
        {
            "to_email": "alice@example.org",
            "requester_name": "Alice Requester",
            "proposal_reference": "VRP-20260601-0001",
            "project_reference": response.json()["collectionUseProject"][
                "referenceNumber"
            ],
            "approved_by_name": "Curator One",
            "link": (
                f"{settings.public_origin}/p/collections/projects/"
                f"{response.json()['collectionUseProject']['id']}"
            ),
        }
    ]


async def test_approve_public_proposal_sends_access_email_after_commit() -> None:
    resolved = ResolvedExternalRequester(
        actor=Actor(
            id=PermissionId("permission-external-1"),
            group=GroupName.EXTERNAL,
            email="pedro@example.test",
        ),
        temporary_password="Temp-Pw-123!",
    )
    requester_provisioner = RecordingRequesterProvisioner(resolved)
    access_email_sender = RecordingAccessEmailSender()

    async with client_with_repos(
        caller=_STAFF_CALLER,
        requester_provisioner=requester_provisioner,
        access_email_sender=access_email_sender,
    ) as (client, _, proposal_repo, _):
        await proposal_repo.add(
            Proposal(
                id=ProposalId("prop-1"),
                reference_number=ReferenceNumber("VRP-20260601-0001"),
                title="Proposal title",
                collection_use_project_id=None,
                intended_use=UseType.IN_SITU_VISIT,
                begin_date=date(2026, 6, 1),
                end_date=date(2026, 6, 7),
                status=ProposalStatus.PENDING,
                requested_by=None,
                requester_contact=RequesterContact(
                    name="Pedro Silva", email=EmailAddress("pedro@example.test")
                ),
                submitted_at=datetime(2026, 6, 7, tzinfo=UTC),
                submission_channel=SubmissionChannel.PUBLIC,
                requested_objects=[
                    RequestedObject(
                        id=RequestedObjectId("requested-object-1"),
                        inventory_number="INV-001",
                        category="manuscript",
                        description="for study",
                        requested_at=datetime(2026, 6, 1, tzinfo=UTC),
                    )
                ],
            )
        )

        response = await client.post(
            "/api/v1/proposals/prop-1/approve",
            json={
                "title": "Approved project",
                "purpose": "Use the collection",
                "beginDate": "2026-06-07",
                "endDate": "2026-06-30",
            },
        )

    assert response.status_code == 200
    assert response.json()["collectionUseProject"]["requestedBy"]["permissionId"] == (
        "permission-external-1"
    )
    # The credentials e-mail is only ever dispatched once the approval (and
    # the request that provisioned it) is committed — see approve_proposal.
    assert access_email_sender.calls == [
        (
            "pedro@example.test",
            "Pedro Silva",
            f"{settings.public_origin}/login",
            "Temp-Pw-123!",
        )
    ]


async def test_approve_public_proposal_new_account_skips_approval_email() -> None:
    resolved = ResolvedExternalRequester(
        actor=Actor(
            id=PermissionId("permission-external-1"),
            group=GroupName.EXTERNAL,
            email="pedro@example.test",
        ),
        temporary_password="Temp-Pw-123!",
    )
    proposal_email_sender = RecordingProposalNotificationEmailSender()

    async with client_with_repos(
        caller=_STAFF_CALLER,
        requester_provisioner=RecordingRequesterProvisioner(resolved),
        proposal_email_sender=proposal_email_sender,
    ) as (client, _, proposal_repo, _):
        await proposal_repo.add(
            Proposal(
                id=ProposalId("prop-1"),
                reference_number=ReferenceNumber("VRP-20260601-0001"),
                title="Proposal title",
                collection_use_project_id=None,
                intended_use=UseType.IN_SITU_VISIT,
                begin_date=date(2026, 6, 1),
                end_date=date(2026, 6, 7),
                status=ProposalStatus.PENDING,
                requested_by=None,
                requester_contact=RequesterContact(
                    name="Pedro Silva", email=EmailAddress("pedro@example.test")
                ),
                submitted_at=datetime(2026, 6, 7, tzinfo=UTC),
                submission_channel=SubmissionChannel.PUBLIC,
            )
        )

        response = await client.post(
            "/api/v1/proposals/prop-1/approve",
            json={
                "title": "Approved project",
                "purpose": "Use the collection",
                "beginDate": "2026-06-07",
                "endDate": "2026-06-30",
            },
        )

    assert response.status_code == 200
    assert proposal_email_sender.approved_calls == []


async def test_approve_public_proposal_existing_account_sends_approval_email() -> None:
    resolved = ResolvedExternalRequester(
        actor=Actor(
            id=PermissionId("permission-external-1"),
            group=GroupName.EXTERNAL,
            email="pedro@example.test",
        ),
        temporary_password=None,
    )
    proposal_email_sender = RecordingProposalNotificationEmailSender()

    async with client_with_repos(
        caller=_STAFF_CALLER,
        permission_records={
            "permission-staff": _permission_record(
                "permission-staff",
                GroupName.CURATORIAL,
                user_name="Curator One",
                user_email="curator@example.org",
            ),
        },
        requester_provisioner=RecordingRequesterProvisioner(resolved),
        proposal_email_sender=proposal_email_sender,
    ) as (client, _, proposal_repo, _):
        await proposal_repo.add(
            Proposal(
                id=ProposalId("prop-1"),
                reference_number=ReferenceNumber("VRP-20260601-0001"),
                title="Proposal title",
                collection_use_project_id=None,
                intended_use=UseType.IN_SITU_VISIT,
                begin_date=date(2026, 6, 1),
                end_date=date(2026, 6, 7),
                status=ProposalStatus.PENDING,
                requested_by=None,
                requester_contact=RequesterContact(
                    name="Pedro Silva", email=EmailAddress("pedro@example.test")
                ),
                submitted_at=datetime(2026, 6, 7, tzinfo=UTC),
                submission_channel=SubmissionChannel.PUBLIC,
            )
        )

        response = await client.post(
            "/api/v1/proposals/prop-1/approve",
            json={
                "title": "Approved project",
                "purpose": "Use the collection",
                "beginDate": "2026-06-07",
                "endDate": "2026-06-30",
            },
        )

    project = response.json()["collectionUseProject"]
    assert response.status_code == 200
    assert proposal_email_sender.approved_calls == [
        {
            "to_email": "pedro@example.test",
            "requester_name": "Pedro Silva",
            "proposal_reference": "VRP-20260601-0001",
            "project_reference": project["referenceNumber"],
            "approved_by_name": "Curator One",
            "link": f"{settings.public_origin}/p/collections/projects/{project['id']}",
        }
    ]


async def test_cancel_proposal_by_requester_without_project_returns_cancelled() -> None:
    async with client_with_repos() as (client, project_repo, proposal_repo, _):
        await proposal_repo.add(_proposal(status=ProposalStatus.SUBMITTED))

        response = await client.post(
            "/api/v1/proposals/prop-1/cancel",
            json={"reason": "Research trip cancelled"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["proposal"]["status"] == "CANCELLED"
    assert body["proposal"]["lastEvent"]["type"] == "CANCELLED"
    assert body["proposal"]["lastEvent"]["note"] == "Research trip cancelled"
    assert body["collectionUseProject"] is None
    assert proposal_repo.items["prop-1"].status == ProposalStatus.CANCELLED
    assert project_repo.items == {}


async def test_cancel_proposal_cascades_to_existing_project_any_status() -> None:
    async with client_with_repos() as (client, project_repo, proposal_repo, _):
        await proposal_repo.add(_proposal(status=ProposalStatus.APPROVED))
        await project_repo.add(_project(status=UseStatus.COMPLETED))

        response = await client.post(
            "/api/v1/proposals/prop-1/cancel",
            json={"reason": "No longer needed"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["proposal"]["status"] == "CANCELLED"
    assert body["collectionUseProject"]["status"] == "CANCELLED"
    assert proposal_repo.items["prop-1"].events[-1].type.value == "CANCELLED"
    assert project_repo.items["proj-1"].status == UseStatus.CANCELLED
    assert project_repo.items["proj-1"].result.value == "CANCELLED"
    assert project_repo.items["proj-1"].events[-1].type.value == "CANCELLED"


async def test_cancel_proposal_rejects_non_requester() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        _,
        proposal_repo,
        _,
    ):
        await proposal_repo.add(_proposal(status=ProposalStatus.PENDING))

        response = await client.post(
            "/api/v1/proposals/prop-1/cancel",
            json={"reason": "Trying to cancel"},
        )

    assert response.status_code == 403
    assert response.json()["error"] == "ACCESS_DENIED"
    assert proposal_repo.items["prop-1"].status == ProposalStatus.PENDING


async def test_cancel_proposal_rejects_rejected_status() -> None:
    async with client_with_repos() as (client, project_repo, proposal_repo, _):
        await proposal_repo.add(_proposal(status=ProposalStatus.REJECTED))
        await project_repo.add(_project(status=UseStatus.CREATED))

        response = await client.post(
            "/api/v1/proposals/prop-1/cancel",
            json={"reason": "No longer needed"},
        )

    assert response.status_code == 409
    assert response.json()["error"] == "INVALID_TRANSITION"
    assert response.json()["message"] == "Cannot cancel a rejected proposal"
    assert proposal_repo.items["prop-1"].status == ProposalStatus.REJECTED
    assert project_repo.items["proj-1"].status == UseStatus.CREATED
    assert project_repo.items["proj-1"].events == []


async def test_submit_document_empty_document_type_returns_422() -> None:
    async with client_with_repos() as (client, _, proposal_repo, _):
        await proposal_repo.add(
            Proposal(
                id=ProposalId("prop-1"),
                reference_number=ReferenceNumber("VRP-20260601-0001"),
                title="Proposal title",
                collection_use_project_id=CollectionUseProjectId("proj-1"),
                intended_use=UseType.IN_SITU_VISIT,
                begin_date=date(2026, 6, 1),
                end_date=date(2026, 6, 7),
                status=ProposalStatus.PENDING,
                requested_by=PermissionId("permission-1"),
                submitted_at=datetime(2026, 6, 7, tzinfo=UTC),
                submission_channel=SubmissionChannel.AUTHENTICATED,
            )
        )

        response = await client.post(
            "/api/v1/proposals/prop-1/documents",
            files={"file": ("request.docx", b"docx", "application/vnd.ms-word")},
            data={"documentType": ""},
            headers={"X-Permission-Id": "permission-1"},
        )

    assert response.status_code == 422
    assert response.json()["message"] == "Validation failed"


def _pending_proposal() -> "Proposal":
    return Proposal(
        id=ProposalId("prop-1"),
        reference_number=ReferenceNumber("VRP-20260601-0001"),
        title="Proposal title",
        collection_use_project_id=CollectionUseProjectId("proj-1"),
        intended_use=UseType.IN_SITU_VISIT,
        begin_date=date(2026, 6, 1),
        end_date=date(2026, 6, 7),
        status=ProposalStatus.PENDING,
        requested_by=PermissionId("permission-1"),
        submitted_at=datetime(2026, 6, 7, tzinfo=UTC),
        submission_channel=SubmissionChannel.AUTHENTICATED,
    )


async def test_submit_document_rejects_non_docx_content() -> None:
    async with client_with_repos() as (client, _, proposal_repo, _):
        await proposal_repo.add(_pending_proposal())
        response = await client.post(
            "/api/v1/proposals/prop-1/documents",
            files={"file": ("request.docx", b"not a real zip", "application/octet")},
            data={"documentType": "REQUEST_FORM"},
            headers={"X-Permission-Id": "permission-1"},
        )
    assert response.status_code == 415
    assert response.json()["error"] == "INVALID_FILE_FORMAT"


async def test_submit_document_accepts_valid_docx() -> None:
    async with client_with_repos() as (client, _, proposal_repo, _):
        await proposal_repo.add(_pending_proposal())
        response = await client.post(
            "/api/v1/proposals/prop-1/documents",
            files={
                "file": (
                    "request.docx",
                    _docx_bytes(),
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
            data={"documentType": "REQUEST_FORM"},
            headers={"X-Permission-Id": "permission-1"},
        )
    assert response.status_code == 201


async def test_submit_document_notifies_assigned_staff_target() -> None:
    notification_dispatcher = RecordingNotificationDispatcher()
    proposal_email_sender = RecordingProposalNotificationEmailSender()
    async with client_with_repos(
        permission_records={
            "permission-1": _permission_record("permission-1", GroupName.EXTERNAL),
            "permission-target": _permission_record(
                "permission-target", GroupName.CURATORIAL
            ),
        },
        notification_dispatcher=notification_dispatcher,
        proposal_email_sender=proposal_email_sender,
    ) as (client, _, proposal_repo, _):
        proposal = _pending_proposal()
        proposal.assigned_to = PermissionId("permission-target")
        await proposal_repo.add(proposal)
        response = await client.post(
            "/api/v1/proposals/prop-1/documents",
            files={
                "file": (
                    "request.docx",
                    _docx_bytes(),
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
            data={"documentType": "REQUEST_FORM"},
            headers={"X-Permission-Id": "permission-1"},
        )

    assert response.status_code == 201
    assert notification_dispatcher.calls == [
        {
            "recipient_permission_id": "permission-target",
            "kind": "PROPOSAL_DOCUMENTS_SUBMITTED",
            "triggered_by": "permission-1",
            "related_resource_type": "PROPOSAL",
            "related_resource_id": "prop-1",
            "related_resource_label": "VRP-20260601-0001",
        }
    ]
    assert proposal_email_sender.documents_submitted_calls == [
        {
            "to_email": "permission-target@example.org",
            "recipient_name": "User permission-target",
            "proposal_reference": "VRP-20260601-0001",
            "submitted_by_name": "User permission-1",
            "link": (
                f"{settings.public_origin}/p/collections/proposals/"
                "my-assignments/prop-1?tab=documents"
            ),
        }
    ]


async def test_submit_document_to_self_sends_no_notification_or_email() -> None:
    notification_dispatcher = RecordingNotificationDispatcher()
    proposal_email_sender = RecordingProposalNotificationEmailSender()
    async with client_with_repos(
        caller=_STAFF_CALLER,
        permission_records={
            "permission-staff": _permission_record(
                "permission-staff", GroupName.CURATORIAL
            )
        },
        notification_dispatcher=notification_dispatcher,
        proposal_email_sender=proposal_email_sender,
    ) as (client, _, proposal_repo, _):
        proposal = _pending_proposal()
        proposal.requested_by = PermissionId("permission-staff")
        proposal.assigned_to = PermissionId("permission-staff")
        await proposal_repo.add(proposal)
        response = await client.post(
            "/api/v1/proposals/prop-1/documents",
            files={
                "file": (
                    "request.docx",
                    _docx_bytes(),
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
            data={"documentType": "REQUEST_FORM"},
        )

    assert response.status_code == 201
    assert notification_dispatcher.calls == []
    assert proposal_email_sender.documents_submitted_calls == []


async def test_download_document_returns_file_bytes() -> None:
    document = Document(
        id=DocumentId("doc-1"),
        type=DocumentType("RESEARCH_FORM"),
        file_name="research_form.docx",
        file_reference="stored.docx",
        submitted_at=datetime(2026, 6, 7, tzinfo=UTC),
        submitted_by=PermissionId("permission-1"),
    )
    async with client_with_repos() as (client, _, proposal_repo, _):
        file_storage = app.dependency_overrides[get_file_storage]()
        file_storage.files["stored.docx"] = b"docx bytes"
        await proposal_repo.add(_proposal(documents=[document]))

        response = await client.get(
            "/api/v1/proposals/prop-1/documents/doc-1",
            headers={"X-Permission-Id": "permission-1"},
        )

    assert response.status_code == 200
    assert response.content == b"docx bytes"
    assert response.headers["content-type"] == (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert response.headers["content-disposition"] == (
        'attachment; filename="research_form.docx"'
    )


async def test_download_document_unknown_document_returns_404() -> None:
    async with client_with_repos() as (client, _, proposal_repo, _):
        await proposal_repo.add(_proposal())

        response = await client.get(
            "/api/v1/proposals/prop-1/documents/missing-doc",
            headers={"X-Permission-Id": "permission-1"},
        )

    assert response.status_code == 404
    assert response.json()["error"] == "NOT_FOUND"
    assert response.json()["message"] == "Document not found for this proposal"


async def test_download_document_rejects_non_owner() -> None:
    document = Document(
        id=DocumentId("doc-1"),
        type=DocumentType("RESEARCH_FORM"),
        file_name="research_form.docx",
        file_reference="stored.docx",
        submitted_at=datetime(2026, 6, 7, tzinfo=UTC),
        submitted_by=PermissionId("permission-other"),
    )
    async with client_with_repos() as (client, _, proposal_repo, _):
        await proposal_repo.add(
            _proposal(
                requested_by=PermissionId("permission-other"),
                documents=[document],
            )
        )

        response = await client.get(
            "/api/v1/proposals/prop-1/documents/doc-1",
            headers={"X-Permission-Id": "permission-1"},
        )

    assert response.status_code == 403
    assert response.json()["error"] == "ACCESS_DENIED"


async def test_log_entry_attachment_invalid_media_type_returns_422() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        project_repo,
        proposal_repo,
        _,
    ):
        project_id = CollectionUseProjectId("project-1")
        await project_repo.add(
            CollectionUseProject(
                id=project_id,
                reference_number=ReferenceNumber("CUP-ABCDEFG1"),
                title="Project",
                purpose="Use collection",
                intended_use=UseType.IN_SITU_VISIT,
                status=UseStatus.CREATED,
                begin_date=date(2026, 6, 1),
                end_date=date(2026, 6, 7),
                requested_by=PermissionId("permission-1"),
            )
        )
        await proposal_repo.add(
            Proposal(
                id=ProposalId("prop-1"),
                reference_number=ReferenceNumber("VRP-20260601-0001"),
                title="Proposal title",
                collection_use_project_id=project_id,
                intended_use=UseType.IN_SITU_VISIT,
                begin_date=date(2026, 6, 1),
                end_date=date(2026, 6, 7),
                status=ProposalStatus.APPROVED,
                requested_by=PermissionId("permission-1"),
                submitted_at=datetime(2026, 6, 7, tzinfo=UTC),
                submission_channel=SubmissionChannel.AUTHENTICATED,
            )
        )
        log_repo = app.dependency_overrides[get_access_log_repo]()
        await log_repo.add(
            ObjectAccessLog(
                id=ObjectAccessLogId("log-1"),
                reference_number=ReferenceNumber("OAL-ABCDEFG1"),
                collection_use_project_id=project_id,
            )
        )
        await log_repo.save_entry(
            ObjectLogEntry(
                id=ObjectLogEntryId("entry-1"),
                object_access_log_id=ObjectAccessLogId("log-1"),
                collection_use_object_id=CollectionUseObjectId("cuo-1"),
                number_of_objects=1,
                added_at=datetime(2026, 6, 7, tzinfo=UTC),
                added_by=PermissionId("permission-staff"),
            )
        )

        response = await client.post(
            "/api/v1/collection-use-projects/project-1/log-entries/entry-1/attachments",
            files={"file": ("photo.jpg", b"jpeg", "image/jpeg")},
            data={
                "mediaType": "NOT_A_MEDIA_TYPE",
                "attachmentDescription": "Front view",
            },
        )

    assert response.status_code == 422
    assert response.json()["error"] == "VALIDATION_ERROR"


async def test_log_entry_attachment_requires_description() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        project_repo,
        proposal_repo,
        _,
    ):
        await project_repo.add(
            _project(
                "project-1",
                status=UseStatus.IN_PROGRESS,
                objects=[_collection_use_object()],
            )
        )
        created = await client.post(
            "/api/v1/collection-use-projects/project-1/log-entries",
            json={"collectionUseObjectId": "cuo-1", "numberOfObjects": 1},
            headers={"X-Permission-Id": "permission-staff"},
        )
        entry_id = created.json()["id"]

        without_description = await client.post(
            f"/api/v1/collection-use-projects/project-1/log-entries/{entry_id}/attachments",
            files={"file": ("missing.pdf", b"pdf", "application/pdf")},
            data={"mediaType": "DOCUMENT"},
            headers={"X-Permission-Id": "permission-staff"},
        )
        blank_description = await client.post(
            f"/api/v1/collection-use-projects/project-1/log-entries/{entry_id}/attachments",
            files={"file": ("blank.pdf", b"pdf", "application/pdf")},
            data={"mediaType": "DOCUMENT", "attachmentDescription": "   "},
            headers={"X-Permission-Id": "permission-staff"},
        )
        with_description = await client.post(
            f"/api/v1/collection-use-projects/project-1/log-entries/{entry_id}/attachments",
            files={"file": ("photo.jpg", b"jpeg", "image/jpeg")},
            data={"mediaType": "IMAGE", "attachmentDescription": "Front view"},
            headers={"X-Permission-Id": "permission-staff"},
        )
        listing = await client.get(
            "/api/v1/collection-use-projects/project-1/log-entries",
            headers={"X-Permission-Id": "permission-staff"},
        )

    assert without_description.status_code == 422
    assert blank_description.status_code == 422
    assert blank_description.json()["error"] == "VALIDATION_ERROR"
    assert with_description.status_code == 201
    assert with_description.json()["attachmentDescription"] == "Front view"
    # The description survives the round-trip through the listing endpoint.
    descriptions = {
        a["attachmentDescription"] for a in listing.json()["content"][0]["attachments"]
    }
    assert descriptions == {"Front view"}


async def test_download_log_entry_attachment_returns_file() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        project_repo,
        proposal_repo,
        _,
    ):
        await project_repo.add(
            _project(
                "project-1",
                status=UseStatus.IN_PROGRESS,
                objects=[_collection_use_object()],
            )
        )
        created = await client.post(
            "/api/v1/collection-use-projects/project-1/log-entries",
            json={"collectionUseObjectId": "cuo-1", "numberOfObjects": 1},
            headers={"X-Permission-Id": "permission-staff"},
        )
        entry_id = created.json()["id"]
        uploaded = await client.post(
            f"/api/v1/collection-use-projects/project-1/log-entries/{entry_id}/attachments",
            files={"file": ("report.pdf", b"%PDF-1.4 bytes", "application/pdf")},
            data={"mediaType": "DOCUMENT", "attachmentDescription": "Visit report"},
            headers={"X-Permission-Id": "permission-staff"},
        )
        file_reference = uploaded.json()["fileReference"]

        download = await client.get(
            f"/api/v1/collection-use-projects/project-1/log-entries/{entry_id}/attachments/{file_reference}",
            headers={"X-Permission-Id": "permission-staff"},
        )

    assert download.status_code == 200
    assert download.content == b"%PDF-1.4 bytes"
    assert download.headers["content-type"].startswith("application/pdf")
    assert "report.pdf" in download.headers["content-disposition"]


async def test_log_entry_attachment_uses_configured_encrypted_storage(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    plaintext = b"plain route payload"
    key = base64.b64encode(b"k" * 32).decode("ascii")
    storage = build_file_storage(tmp_path, key)
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "file_encryption_key", key)

    async with client_with_repos(caller=_STAFF_CALLER, file_storage=storage) as (
        client,
        project_repo,
        _,
        _conversation_repo,
    ):
        await project_repo.add(
            _project(
                "project-1",
                status=UseStatus.IN_PROGRESS,
                objects=[_collection_use_object()],
            )
        )
        created = await client.post(
            "/api/v1/collection-use-projects/project-1/log-entries",
            json={"collectionUseObjectId": "cuo-1", "numberOfObjects": 1},
            headers={"X-Permission-Id": "permission-staff"},
        )
        entry_id = created.json()["id"]
        uploaded = await client.post(
            f"/api/v1/collection-use-projects/project-1/log-entries/{entry_id}/attachments",
            files={"file": ("route.txt", plaintext, "text/plain")},
            data={"mediaType": "DOCUMENT", "attachmentDescription": "Route payload"},
            headers={"X-Permission-Id": "permission-staff"},
        )
        file_reference = uploaded.json()["fileReference"]
        blob_path = tmp_path / file_reference
        blob = blob_path.read_bytes()

        download = await client.get(
            f"/api/v1/collection-use-projects/project-1/log-entries/{entry_id}/attachments/{file_reference}",
            headers={"X-Permission-Id": "permission-staff"},
        )
        moved_reference = f"{file_reference}.moved"
        await storage.save(plaintext, moved_reference)
        blob_path.write_bytes((tmp_path / moved_reference).read_bytes())
        unreadable = await client.get(
            f"/api/v1/collection-use-projects/project-1/log-entries/{entry_id}/attachments/{file_reference}",
            headers={"X-Permission-Id": "permission-staff"},
        )

    assert blob.startswith(b"\x01")
    assert plaintext not in blob
    assert download.status_code == 200
    assert download.content == plaintext
    assert unreadable.status_code == 500
    assert unreadable.json()["error"] == "FILE_UNREADABLE"


async def test_download_log_entry_attachment_unknown_reference_returns_404() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        project_repo,
        proposal_repo,
        _,
    ):
        await project_repo.add(
            _project(
                "project-1",
                status=UseStatus.IN_PROGRESS,
                objects=[_collection_use_object()],
            )
        )
        created = await client.post(
            "/api/v1/collection-use-projects/project-1/log-entries",
            json={"collectionUseObjectId": "cuo-1", "numberOfObjects": 1},
            headers={"X-Permission-Id": "permission-staff"},
        )
        entry_id = created.json()["id"]

        response = await client.get(
            f"/api/v1/collection-use-projects/project-1/log-entries/{entry_id}/attachments/does-not-exist",
            headers={"X-Permission-Id": "permission-staff"},
        )

    assert response.status_code == 404
    assert response.json()["error"] == "ATTACHMENT_NOT_FOUND"


async def test_delete_log_entry_attachment_removes_file() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        project_repo,
        proposal_repo,
        _,
    ):
        await project_repo.add(
            _project(
                "project-1",
                status=UseStatus.IN_PROGRESS,
                objects=[_collection_use_object()],
            )
        )
        created = await client.post(
            "/api/v1/collection-use-projects/project-1/log-entries",
            json={"collectionUseObjectId": "cuo-1", "numberOfObjects": 1},
            headers={"X-Permission-Id": "permission-staff"},
        )
        entry_id = created.json()["id"]
        uploaded = await client.post(
            f"/api/v1/collection-use-projects/project-1/log-entries/{entry_id}/attachments",
            files={"file": ("report.pdf", b"%PDF-1.4 bytes", "application/pdf")},
            data={"mediaType": "DOCUMENT", "attachmentDescription": "Visit report"},
            headers={"X-Permission-Id": "permission-staff"},
        )
        file_reference = uploaded.json()["fileReference"]

        deleted = await client.delete(
            f"/api/v1/collection-use-projects/project-1/log-entries/{entry_id}/attachments/{file_reference}",
            headers={"X-Permission-Id": "permission-staff"},
        )
        download = await client.get(
            f"/api/v1/collection-use-projects/project-1/log-entries/{entry_id}/attachments/{file_reference}",
            headers={"X-Permission-Id": "permission-staff"},
        )

    assert deleted.status_code == 204
    assert download.status_code == 404
    assert download.json()["error"] == "ATTACHMENT_NOT_FOUND"


async def test_download_occurrence_entry_attachment_returns_file() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        project_repo,
        proposal_repo,
        _,
    ):
        await project_repo.add(
            _project(
                "project-1",
                status=UseStatus.IN_PROGRESS,
                objects=[_collection_use_object()],
            )
        )
        created = await client.post(
            "/api/v1/collection-use-projects/project-1/occurrence-entries",
            json={
                "collectionUseObjectId": "cuo-1",
                "numberOfObjects": 1,
                "occurrenceDate": "2026-06-03T11:30:00Z",
                "location": "Lab",
                "detailedDescription": "desc",
            },
            headers={"X-Permission-Id": "permission-staff"},
        )
        entry_id = created.json()["id"]
        uploaded = await client.post(
            f"/api/v1/collection-use-projects/project-1/occurrence-entries/{entry_id}/attachments",
            files={"file": ("photo.jpg", b"jpegbytes", "image/jpeg")},
            data={"mediaType": "IMAGE", "attachmentDescription": "Occurrence photo"},
            headers={"X-Permission-Id": "permission-staff"},
        )
        file_reference = uploaded.json()["fileReference"]

        download = await client.get(
            f"/api/v1/collection-use-projects/project-1/occurrence-entries/{entry_id}/attachments/{file_reference}",
            headers={"X-Permission-Id": "permission-staff"},
        )

    assert download.status_code == 200
    assert download.content == b"jpegbytes"
    assert download.headers["content-type"].startswith("image/jpeg")
    assert "photo.jpg" in download.headers["content-disposition"]


async def test_occurrence_entry_attachment_requires_description() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        project_repo,
        proposal_repo,
        _,
    ):
        await project_repo.add(
            _project(
                "project-1",
                status=UseStatus.IN_PROGRESS,
                objects=[_collection_use_object()],
            )
        )
        created = await client.post(
            "/api/v1/collection-use-projects/project-1/occurrence-entries",
            json={
                "collectionUseObjectId": "cuo-1",
                "numberOfObjects": 1,
                "occurrenceDate": "2026-06-03T11:30:00Z",
                "location": "Lab",
                "detailedDescription": "desc",
            },
            headers={"X-Permission-Id": "permission-staff"},
        )
        entry_id = created.json()["id"]

        without_description = await client.post(
            f"/api/v1/collection-use-projects/project-1/occurrence-entries/{entry_id}/attachments",
            files={"file": ("photo.jpg", b"jpegbytes", "image/jpeg")},
            data={"mediaType": "IMAGE"},
            headers={"X-Permission-Id": "permission-staff"},
        )
        blank_description = await client.post(
            f"/api/v1/collection-use-projects/project-1/occurrence-entries/{entry_id}/attachments",
            files={"file": ("photo.jpg", b"jpegbytes", "image/jpeg")},
            data={"mediaType": "IMAGE", "attachmentDescription": "   "},
            headers={"X-Permission-Id": "permission-staff"},
        )

    assert without_description.status_code == 422
    assert blank_description.status_code == 422
    assert blank_description.json()["error"] == "VALIDATION_ERROR"


async def test_delete_occurrence_entry_attachment_removes_file() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        project_repo,
        proposal_repo,
        _,
    ):
        await project_repo.add(
            _project(
                "project-1",
                status=UseStatus.IN_PROGRESS,
                objects=[_collection_use_object()],
            )
        )
        created = await client.post(
            "/api/v1/collection-use-projects/project-1/occurrence-entries",
            json={
                "collectionUseObjectId": "cuo-1",
                "numberOfObjects": 1,
                "occurrenceDate": "2026-06-03T11:30:00Z",
                "location": "Lab",
                "detailedDescription": "desc",
            },
            headers={"X-Permission-Id": "permission-staff"},
        )
        entry_id = created.json()["id"]
        uploaded = await client.post(
            f"/api/v1/collection-use-projects/project-1/occurrence-entries/{entry_id}/attachments",
            files={"file": ("photo.jpg", b"jpegbytes", "image/jpeg")},
            data={"mediaType": "IMAGE", "attachmentDescription": "Occurrence photo"},
            headers={"X-Permission-Id": "permission-staff"},
        )
        file_reference = uploaded.json()["fileReference"]

        deleted = await client.delete(
            f"/api/v1/collection-use-projects/project-1/occurrence-entries/{entry_id}/attachments/{file_reference}",
            headers={"X-Permission-Id": "permission-staff"},
        )
        download = await client.get(
            f"/api/v1/collection-use-projects/project-1/occurrence-entries/{entry_id}/attachments/{file_reference}",
            headers={"X-Permission-Id": "permission-staff"},
        )

    assert deleted.status_code == 204
    assert download.status_code == 404
    assert download.json()["error"] == "ATTACHMENT_NOT_FOUND"


async def test_add_log_entry_returns_201_with_access_log_created() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        project_repo,
        proposal_repo,
        _,
    ):
        await project_repo.add(
            _project(
                "project-1",
                status=UseStatus.IN_PROGRESS,
                objects=[_collection_use_object()],
            )
        )

        response = await client.post(
            "/api/v1/collection-use-projects/project-1/log-entries",
            json={
                "collectionUseObjectId": "cuo-1",
                "numberOfObjects": 2,
                "observations": "Handled with gloves",
            },
            headers={"X-Permission-Id": "permission-staff"},
        )

        assert response.status_code == 201
        body = response.json()
        assert body["collectionUseObjectId"] == "cuo-1"
        assert body["numberOfObjects"] == 2
        assert body["observations"] == "Handled with gloves"
        assert body["attachments"] == []

        listing = await client.get(
            "/api/v1/collection-use-projects/project-1/log-entries",
            headers={"X-Permission-Id": "permission-staff"},
        )

    assert listing.status_code == 200
    listing_body = listing.json()
    assert listing_body["accessLog"]["referenceNumber"].startswith("OAL-")
    assert listing_body["accessLog"]["dateConclusion"] is None
    assert listing_body["accessLog"]["curator"] is None
    assert listing_body["totalElements"] == 1
    assert listing_body["content"][0]["numberOfObjects"] == 2


async def test_edit_log_entry_updates_editable_fields() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        project_repo,
        proposal_repo,
        _,
    ):
        await project_repo.add(
            _project(
                "project-1",
                status=UseStatus.IN_PROGRESS,
                objects=[_collection_use_object()],
            )
        )
        created = await client.post(
            "/api/v1/collection-use-projects/project-1/log-entries",
            json={
                "collectionUseObjectId": "cuo-1",
                "numberOfObjects": 2,
                "observations": "original",
            },
            headers={"X-Permission-Id": "permission-staff"},
        )
        entry_id = created.json()["id"]

        edited = await client.patch(
            f"/api/v1/collection-use-projects/project-1/log-entries/{entry_id}",
            json={
                "addedAt": "2025-06-03T14:00:00",
                "numberOfObjects": 5,
                "observations": "corrected",
            },
            headers={"X-Permission-Id": "permission-staff"},
        )

    assert edited.status_code == 200
    body = edited.json()
    assert body["id"] == entry_id
    assert body["numberOfObjects"] == 5
    assert body["observations"] == "corrected"
    assert body["addedAt"] == "2025-06-03T14:00:00"
    # Immutable fields are preserved.
    assert body["collectionUseObjectId"] == "cuo-1"
    assert body["addedBy"]["permissionId"] == "permission-staff"


async def test_edit_log_entry_is_partial_and_clears_observations() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        project_repo,
        proposal_repo,
        _,
    ):
        await project_repo.add(
            _project(
                "project-1",
                status=UseStatus.IN_PROGRESS,
                objects=[_collection_use_object()],
            )
        )
        created = await client.post(
            "/api/v1/collection-use-projects/project-1/log-entries",
            json={
                "collectionUseObjectId": "cuo-1",
                "numberOfObjects": 2,
                "observations": "original",
            },
            headers={"X-Permission-Id": "permission-staff"},
        )
        entry_id = created.json()["id"]

        # Omitting numberOfObjects leaves it untouched; null clears observations.
        edited = await client.patch(
            f"/api/v1/collection-use-projects/project-1/log-entries/{entry_id}",
            json={"observations": None},
            headers={"X-Permission-Id": "permission-staff"},
        )

    assert edited.status_code == 200
    body = edited.json()
    assert body["numberOfObjects"] == 2
    assert body["observations"] is None


async def test_edit_log_entry_unknown_entry_returns_404() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        project_repo,
        _,
        _,
    ):
        await project_repo.add(_project("project-1", status=UseStatus.IN_PROGRESS))

        response = await client.patch(
            "/api/v1/collection-use-projects/project-1/log-entries/missing",
            json={"numberOfObjects": 3},
            headers={"X-Permission-Id": "permission-staff"},
        )

    assert response.status_code == 404
    assert response.json()["error"] == "ENTRY_NOT_FOUND"


async def test_log_entry_links_to_requested_object_over_http() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        project_repo,
        proposal_repo,
        _,
    ):
        await project_repo.add(
            _project(
                "project-1",
                status=UseStatus.IN_PROGRESS,
                objects=[_collection_use_object()],
            )
        )

        ok = await client.post(
            "/api/v1/collection-use-projects/project-1/log-entries",
            json={
                "numberOfObjects": 1,
                "collectionUseObjectId": "cuo-1",
            },
            headers={"X-Permission-Id": "permission-staff"},
        )
        unknown = await client.post(
            "/api/v1/collection-use-projects/project-1/log-entries",
            json={
                "numberOfObjects": 1,
                "collectionUseObjectId": "does-not-exist",
            },
            headers={"X-Permission-Id": "permission-staff"},
        )

    assert ok.status_code == 201
    assert ok.json()["collectionUseObjectId"] == "cuo-1"
    assert unknown.status_code == 422
    assert unknown.json()["error"] == "VALIDATION_ERROR"


async def test_get_object_access_log_returns_404_without_entries() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        project_repo,
        _,
        _,
    ):
        await project_repo.add(_project("project-1", status=UseStatus.IN_PROGRESS))

        response = await client.get(
            "/api/v1/collection-use-projects/project-1/object-access-log",
            headers={"X-Permission-Id": "permission-staff"},
        )

    assert response.status_code == 404
    assert response.json()["error"] == "OBJECT_ACCESS_LOG_NOT_FOUND"


async def _seed_access_log_for_document(
    project_repo: InMemoryProjectRepository,
) -> InMemoryAccessLogRepository:
    logged_object = CollectionUseObject(
        id=CollectionUseObjectId("cuo-1"),
        inventory_number="INV-001",
        category="peles",
        description="a fox head",
        requested_at=datetime(2026, 6, 1, tzinfo=UTC),
        requested_by=PermissionId("permission-1"),
        display_title="Vulpes vulpes",
        collection_name="Zoologia",
    )
    await project_repo.add(
        _project("proj-1", status=UseStatus.IN_PROGRESS, objects=[logged_object])
    )
    access_log_repo = app.dependency_overrides[get_access_log_repo]()
    await access_log_repo.add(
        ObjectAccessLog(
            id=ObjectAccessLogId("log-1"),
            reference_number=ReferenceNumber("OL-MUHNAC/COL/2026/0001"),
            collection_use_project_id=CollectionUseProjectId("proj-1"),
            date_conclusion=datetime(2026, 6, 9, tzinfo=UTC),
            curator=PermissionId("permission-staff"),
        )
    )
    await access_log_repo.save_entry(
        ObjectLogEntry(
            id=ObjectLogEntryId("entry-1"),
            object_access_log_id=ObjectAccessLogId("log-1"),
            collection_use_object_id=CollectionUseObjectId("cuo-1"),
            number_of_objects=3,
            added_at=datetime(2026, 6, 2, tzinfo=UTC),
            added_by=PermissionId("permission-staff"),
            observations="Handled with gloves",
        )
    )
    return access_log_repo


async def test_download_object_access_log_document_fills_the_rais_form() -> None:
    async with client_with_repos(
        caller=_STAFF_CALLER,
        permission_records={
            "permission-1": _permission_record(
                "permission-1",
                GroupName.EXTERNAL,
                user_name="Ana Silva",
                user_email="ana@example.org",
            ),
            "permission-staff": _permission_record(
                "permission-staff",
                GroupName.CURATORIAL,
                user_name="Nuno Curador",
            ),
        },
    ) as (client, project_repo, _, _):
        await _seed_access_log_for_document(project_repo)

        response = await client.get(
            "/api/v1/collection-use-projects/proj-1/object-access-log/document",
            headers={"X-Permission-Id": "permission-staff"},
        )

    assert response.status_code == 200
    assert response.headers["content-type"] == DOCX_MEDIA_TYPE
    assert (
        "OL-MUHNAC-COL-2026-0001-RAIS.docx" in response.headers["content-disposition"]
    )

    document = DocxDocument(io.BytesIO(response.content))
    header = [cell.text for cell in document.tables[0].rows[2].cells]
    assert header[0] == "OL-MUHNAC/COL/2026/0001"
    assert header[1] == "RAIS"
    assert header[3] == "Ana Silva"

    identification = {
        row.cells[0].text.split("\n")[0]: row.cells[1].text
        for row in document.tables[1].rows
    }
    assert identification["Nome"] == "Ana Silva"
    assert identification["Email"] == "ana@example.org"
    assert identification["Coleção"] == "Zoologia"
    assert identification["Curador"] == "Nuno Curador"

    objects = document.tables[2]
    assert [cell.text for cell in objects.rows[1].cells] == [
        "INV-001",
        "Vulpes vulpes",
        "peles",
        "3",
        "02-06-2026",
        "Handled with gloves",
    ]
    # One header row plus the form's fifteen object lines: a short log is padded
    # with blanks rather than shrinking the museum's form.
    assert len(objects.rows) == 16
    assert [cell.text for cell in objects.rows[2].cells] == [""] * 6
    assert document.tables[3].rows[1].cells[1].text == "09-06-2026"


async def test_download_object_access_log_document_is_denied_to_other_researchers() -> (
    None
):
    other_researcher = Actor(
        id=PermissionId("permission-9"),
        group=GroupName.EXTERNAL,
        email="mallory@example.org",
    )
    async with client_with_repos(caller=other_researcher) as (
        client,
        project_repo,
        proposal_repo,
        _,
    ):
        await _seed_access_log_for_document(project_repo)
        await proposal_repo.add(_proposal())

        response = await client.get(
            "/api/v1/collection-use-projects/proj-1/object-access-log/document",
            headers={"X-Permission-Id": "permission-9"},
        )

    assert response.status_code == 403


async def test_download_object_access_log_document_falls_back_to_proposal_contact() -> (
    None
):
    """A citizen whose proposal has not been provisioned into Identity yet still
    names the researcher on the form."""
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        project_repo,
        proposal_repo,
        _,
    ):
        await _seed_access_log_for_document(project_repo)
        proposal = _proposal()
        proposal.requester_contact = RequesterContact(
            name="Pedro Silva", email=EmailAddress("pedro@example.test")
        )
        await proposal_repo.add(proposal)

        response = await client.get(
            "/api/v1/collection-use-projects/proj-1/object-access-log/document",
            headers={"X-Permission-Id": "permission-staff"},
        )

    assert response.status_code == 200
    identification = {
        row.cells[0].text.split("\n")[0]: row.cells[1].text
        for row in DocxDocument(io.BytesIO(response.content)).tables[1].rows
    }
    assert identification["Nome"] == "Pedro Silva"
    assert identification["Email"] == "pedro@example.test"


async def test_download_object_access_log_document_returns_404_without_log() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        project_repo,
        _,
        _,
    ):
        await project_repo.add(_project("proj-1", status=UseStatus.IN_PROGRESS))

        response = await client.get(
            "/api/v1/collection-use-projects/proj-1/object-access-log/document",
            headers={"X-Permission-Id": "permission-staff"},
        )

    assert response.status_code == 404
    assert response.json()["error"] == "OBJECT_ACCESS_LOG_NOT_FOUND"


async def _seed_occurrence_for_document(
    project_repo: InMemoryProjectRepository,
) -> InMemoryOccurrenceLogRepository:
    affected_object = CollectionUseObject(
        id=CollectionUseObjectId("cuo-1"),
        inventory_number="INV-001",
        category="peles",
        description="a fox head",
        requested_at=datetime(2026, 6, 1, tzinfo=UTC),
        requested_by=PermissionId("permission-1"),
        display_title="Roaz-corvineiro, Tursiops truncatus",
        collection_name="Zoologia",
    )
    other_object = CollectionUseObject(
        id=CollectionUseObjectId("cuo-2"),
        inventory_number="INV-002",
        category="documentos",
        description="a field notebook",
        requested_at=datetime(2026, 6, 1, tzinfo=UTC),
        requested_by=PermissionId("permission-1"),
        display_title="Caderno de campo",
        collection_name="Arquivo",
    )
    await project_repo.add(
        _project(
            "proj-1",
            status=UseStatus.IN_PROGRESS,
            objects=[affected_object, other_object],
        )
    )
    occurrence_log_repo = app.dependency_overrides[get_occurrence_log_repo]()
    await occurrence_log_repo.add(
        ObjectOccurrenceLog(
            id=ObjectOccurrenceLogId("occ-log-1"),
            reference_number=ReferenceNumber("OO-MUHNAC/COL/2026/0001"),
            collection_use_project_id=CollectionUseProjectId("proj-1"),
        )
    )
    # Two occurrences of the same object, seeded newest first so the report has
    # to order them.
    await occurrence_log_repo.save_entry(
        ObjectOccurrenceEntry(
            id=ObjectOccurrenceEntryId("occ-entry-2"),
            object_occurrence_log_id=ObjectOccurrenceLogId("occ-log-1"),
            collection_use_object_id=CollectionUseObjectId("cuo-2"),
            number_of_objects=1,
            occurrence_date=datetime(2026, 7, 8, tzinfo=UTC),
            location="Sala 1, exposição",
            reported_by=PermissionId("permission-1"),
            detailed_description="Segunda ocorrência.",
        )
    )
    await occurrence_log_repo.save_entry(
        ObjectOccurrenceEntry(
            id=ObjectOccurrenceEntryId("occ-entry-1"),
            object_occurrence_log_id=ObjectOccurrenceLogId("occ-log-1"),
            collection_use_object_id=CollectionUseObjectId("cuo-1"),
            number_of_objects=2,
            occurrence_date=datetime(2026, 6, 2, tzinfo=UTC),
            location="Sala 3, reserva",
            reported_by=PermissionId("permission-staff"),
            detailed_description="Primeira linha.\nSegunda linha.",
            testimonial="Hugo Martins",
            attachments=[
                Attachment(
                    file_reference="occurrences/occ-entry-1/before.jpg",
                    file_name="before.jpg",
                    media_type=MediaType.IMAGE,
                    uploaded_at=datetime(2026, 6, 3, tzinfo=UTC),
                    description="Antes",
                )
            ],
        )
    )
    return occurrence_log_repo


async def test_download_object_occurrence_document_fills_the_roc_form() -> None:
    async with client_with_repos(
        caller=_STAFF_CALLER,
        permission_records={
            "permission-1": _permission_record(
                "permission-1",
                GroupName.EXTERNAL,
                user_name="Ana Silva",
            ),
            "permission-staff": _permission_record(
                "permission-staff",
                GroupName.CURATORIAL,
                user_name="Nuno Curador",
            ),
        },
    ) as (client, project_repo, _, _):
        await _seed_occurrence_for_document(project_repo)

        response = await client.get(
            "/api/v1/collection-use-projects/proj-1/object-occurrence-log/document",
            headers={"X-Permission-Id": "permission-staff"},
        )

    assert response.status_code == 200
    assert response.headers["content-type"] == DOCX_MEDIA_TYPE
    assert (
        "OO-MUHNAC-COL-2026-0001-ROC.docx" in response.headers["content-disposition"]
    )

    document = DocxDocument(io.BytesIO(response.content))
    header = [cell.text for cell in document.tables[0].rows[2].cells]
    assert header[0] == "OO-MUHNAC/COL/2026/0001"
    assert header[1] == "ROC"
    assert header[3] == "Ana Silva"

    fields = document.tables[1]
    # The whole information table repeats, so every block names its own object.
    labels = [row.cells[0].text.split("\n")[0].strip() for row in fields.rows]
    assert labels == [
        "Coleção",
        "Designação do(s) objeto(s)",
        "Nº(s) Inventário",
        "Data",
        "Local",
        "Descrição detalhada",
        "Depoimentos recolhidos (se aplicável)",
        "Imagens",
    ] * 2

    values = [row.cells[1].text for row in fields.rows]
    # Oldest first, across objects. The form has no quantity field, so the count
    # rides with the inventory number.
    assert values[:8] == [
        "Zoologia",
        "Roaz-corvineiro, Tursiops truncatus",
        "INV-001 (2 objetos)",
        "02-06-2026",
        "Sala 3, reserva",
        "Primeira linha.\nSegunda linha.",
        "Hugo Martins",
        "before.jpg — Antes",
    ]
    assert values[8:] == [
        "Arquivo",
        "Caderno de campo",
        "INV-002",
        "08-07-2026",
        "Sala 1, exposição",
        "Segunda ocorrência.",
        "",
        "",
    ]
    # The blank form's instruction text is replaced, not appended to.
    assert "Identificar a coleção" not in values[0]

    # The form signs off once; both reporters are named.
    assert document.tables[2].rows[0].cells[1].text == "Nuno Curador; Ana Silva"


async def test_download_object_occurrence_document_returns_404_without_log() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        project_repo,
        _,
        _,
    ):
        await project_repo.add(
            _project(
                "proj-1",
                status=UseStatus.IN_PROGRESS,
                objects=[_collection_use_object()],
            )
        )

        response = await client.get(
            "/api/v1/collection-use-projects/proj-1/object-occurrence-log/document",
            headers={"X-Permission-Id": "permission-staff"},
        )

    assert response.status_code == 404
    assert response.json()["error"] == "OBJECT_OCCURRENCE_LOG_NOT_FOUND"


async def test_add_occurrence_entry_returns_201_with_occurrence_log_created() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        project_repo,
        proposal_repo,
        _,
    ):
        await project_repo.add(
            _project(
                "project-1",
                status=UseStatus.IN_PROGRESS,
                objects=[_collection_use_object()],
            )
        )

        response = await client.post(
            "/api/v1/collection-use-projects/project-1/occurrence-entries",
            json={
                "collectionUseObjectId": "cuo-1",
                "numberOfObjects": 2,
                "occurrenceDate": "2026-06-03T11:30:00Z",
                "location": "Conservation lab",
                "detailedDescription": "Minor abrasion observed",
                "testimonial": "Reported by the conservator",
            },
            headers={"X-Permission-Id": "permission-staff"},
        )

        assert response.status_code == 201
        body = response.json()
        assert body["collectionUseObjectId"] == "cuo-1"
        assert body["numberOfObjects"] == 2
        assert body["location"] == "Conservation lab"
        assert body["detailedDescription"] == "Minor abrasion observed"
        assert body["testimonial"] == "Reported by the conservator"
        assert body["attachments"] == []

        listing = await client.get(
            "/api/v1/collection-use-projects/project-1/occurrence-entries",
            headers={"X-Permission-Id": "permission-staff"},
        )

    assert listing.status_code == 200
    listing_body = listing.json()
    assert listing_body["occurrenceLog"]["referenceNumber"].startswith("OOL-")
    assert listing_body["occurrenceLog"]["dateConclusion"] is None
    assert listing_body["occurrenceLog"]["curator"] is None
    assert listing_body["totalElements"] == 1
    assert listing_body["content"][0]["numberOfObjects"] == 2


def _add_occurrence_entry_payload() -> dict[str, object]:
    return {
        "collectionUseObjectId": "cuo-1",
        "numberOfObjects": 2,
        "occurrenceDate": "2026-06-03T11:30:00Z",
        "location": "Conservation lab",
        "detailedDescription": "Minor abrasion observed",
        "testimonial": "Reported by the conservator",
    }


async def test_edit_occurrence_entry_updates_editable_fields() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        project_repo,
        proposal_repo,
        _,
    ):
        await project_repo.add(
            _project(
                "project-1",
                status=UseStatus.IN_PROGRESS,
                objects=[_collection_use_object()],
            )
        )
        created = await client.post(
            "/api/v1/collection-use-projects/project-1/occurrence-entries",
            json=_add_occurrence_entry_payload(),
            headers={"X-Permission-Id": "permission-staff"},
        )
        entry_id = created.json()["id"]

        edited = await client.patch(
            f"/api/v1/collection-use-projects/project-1/occurrence-entries/{entry_id}",
            json={
                "numberOfObjects": 5,
                "occurrenceDate": "2026-06-04T09:00:00Z",
                "location": "Main gallery",
                "detailedDescription": "Re-examined under raking light",
                "testimonial": "Confirmed by the curator",
            },
            headers={"X-Permission-Id": "permission-staff"},
        )

    assert edited.status_code == 200
    body = edited.json()
    assert body["id"] == entry_id
    assert body["numberOfObjects"] == 5
    assert body["occurrenceDate"] == "2026-06-04T09:00:00Z"
    assert body["location"] == "Main gallery"
    assert body["detailedDescription"] == "Re-examined under raking light"
    assert body["testimonial"] == "Confirmed by the curator"
    # Immutable fields are preserved.
    assert body["collectionUseObjectId"] == "cuo-1"
    assert body["reportedBy"]["permissionId"] == "permission-staff"


async def test_edit_occurrence_entry_is_partial_and_clears_testimonial() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        project_repo,
        proposal_repo,
        _,
    ):
        await project_repo.add(
            _project(
                "project-1",
                status=UseStatus.IN_PROGRESS,
                objects=[_collection_use_object()],
            )
        )
        created = await client.post(
            "/api/v1/collection-use-projects/project-1/occurrence-entries",
            json=_add_occurrence_entry_payload(),
            headers={"X-Permission-Id": "permission-staff"},
        )
        entry_id = created.json()["id"]

        # Omitting other fields leaves them untouched; null clears testimonial.
        edited = await client.patch(
            f"/api/v1/collection-use-projects/project-1/occurrence-entries/{entry_id}",
            json={"testimonial": None},
            headers={"X-Permission-Id": "permission-staff"},
        )

    assert edited.status_code == 200
    body = edited.json()
    assert body["numberOfObjects"] == 2
    assert body["location"] == "Conservation lab"
    assert body["detailedDescription"] == "Minor abrasion observed"
    assert body["testimonial"] is None


async def test_edit_occurrence_entry_unknown_entry_returns_404() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        project_repo,
        _,
        _,
    ):
        await project_repo.add(_project("project-1", status=UseStatus.IN_PROGRESS))

        response = await client.patch(
            "/api/v1/collection-use-projects/project-1/occurrence-entries/missing",
            json={"numberOfObjects": 3},
            headers={"X-Permission-Id": "permission-staff"},
        )

    assert response.status_code == 404
    assert response.json()["error"] == "ENTRY_NOT_FOUND"


async def test_get_object_occurrence_log_returns_404_without_entries() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        project_repo,
        _,
        _,
    ):
        await project_repo.add(_project("project-1", status=UseStatus.IN_PROGRESS))

        response = await client.get(
            "/api/v1/collection-use-projects/project-1/object-occurrence-log",
            headers={"X-Permission-Id": "permission-staff"},
        )

    assert response.status_code == 404
    assert response.json()["error"] == "OBJECT_OCCURRENCE_LOG_NOT_FOUND"


# ── Publication log ──────────────────────────────────────────────────────────


def _project_proposal(
    requested_by: str = "permission-1",
    assigned_to: str | None = None,
) -> Proposal:
    """A proposal linked to project-1 (for project-access + curator snapshot)."""
    proposal = _proposal("prop-pub", requested_by=PermissionId(requested_by))
    proposal.collection_use_project_id = CollectionUseProjectId("project-1")
    if assigned_to is not None:
        proposal.assigned_to = PermissionId(assigned_to)
    return proposal


async def test_add_publication_entry_in_progress_external_creates_log() -> None:
    async with client_with_repos(caller=_CALLER) as (
        client,
        project_repo,
        proposal_repo,
        _,
    ):
        await project_repo.add(_project("project-1", status=UseStatus.IN_PROGRESS))
        await proposal_repo.add(_project_proposal(assigned_to="permission-staff"))

        response = await client.post(
            "/api/v1/collection-use-projects/project-1/publication-entries",
            json={"note": "Published an article in the museum journal"},
            headers={"X-Permission-Id": "permission-1"},
        )

        assert response.status_code == 201
        body = response.json()
        assert body["note"] == "Published an article in the museum journal"
        assert body["addedBy"]["permissionId"] == "permission-1"
        assert body["attachments"] == []

        listing = await client.get(
            "/api/v1/collection-use-projects/project-1/publication-entries",
            headers={"X-Permission-Id": "permission-1"},
        )

    assert listing.status_code == 200
    listing_body = listing.json()
    assert listing_body["publicationLog"]["referenceNumber"].startswith("PUB-")
    # curator is the informational snapshot of the proposal's assignee
    assert listing_body["publicationLog"]["curator"]["permissionId"] == (
        "permission-staff"
    )
    assert listing_body["totalElements"] == 1
    assert listing_body["content"][0]["note"].startswith("Published")


async def test_add_publication_entry_with_collection_use_object_id() -> None:
    async with client_with_repos(caller=_CALLER) as (
        client,
        project_repo,
        proposal_repo,
        _,
    ):
        await project_repo.add(
            _project(
                "project-1",
                status=UseStatus.IN_PROGRESS,
                objects=[_collection_use_object("cuo-1", "MB03-000827")],
            )
        )
        await proposal_repo.add(_project_proposal())

        response = await client.post(
            "/api/v1/collection-use-projects/project-1/publication-entries",
            json={
                "note": "Heyning & Dahlheim, Orcinus orca",
                "collectionUseObjectId": "cuo-1",
            },
            headers={"X-Permission-Id": "permission-1"},
        )

    assert response.status_code == 201
    body = response.json()
    assert body["collectionUseObjectId"] == "cuo-1"
    assert body["objectReference"]["inventoryNumber"] == "MB03-000827"


async def test_add_publication_entry_rejects_foreign_collection_use_object_id() -> None:
    async with client_with_repos(caller=_CALLER) as (
        client,
        project_repo,
        proposal_repo,
        _,
    ):
        await project_repo.add(_project("project-1", status=UseStatus.IN_PROGRESS))
        await proposal_repo.add(_project_proposal())

        response = await client.post(
            "/api/v1/collection-use-projects/project-1/publication-entries",
            json={
                "note": "References an object outside this project",
                "collectionUseObjectId": "not-in-this-project",
            },
            headers={"X-Permission-Id": "permission-1"},
        )

    assert response.status_code == 422
    assert response.json()["error"] == "VALIDATION_ERROR"


async def test_add_publication_entry_staff_while_in_progress_rejected() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        project_repo,
        _,
        _,
    ):
        await project_repo.add(_project("project-1", status=UseStatus.IN_PROGRESS))

        response = await client.post(
            "/api/v1/collection-use-projects/project-1/publication-entries",
            json={"note": "Staff cannot write while in progress"},
            headers={"X-Permission-Id": "permission-staff"},
        )

    assert response.status_code == 403
    assert response.json()["error"] == "ACCESS_DENIED"


async def test_add_publication_entry_staff_once_completed_ok() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        project_repo,
        _,
        _,
    ):
        await project_repo.add(_project("project-1", status=UseStatus.COMPLETED))

        response = await client.post(
            "/api/v1/collection-use-projects/project-1/publication-entries",
            json={"note": "Final exhibition catalogue entry"},
            headers={"X-Permission-Id": "permission-staff"},
        )

    assert response.status_code == 201
    assert response.json()["note"] == "Final exhibition catalogue entry"


async def test_add_publication_entry_external_once_completed_rejected() -> None:
    async with client_with_repos(caller=_CALLER) as (
        client,
        project_repo,
        proposal_repo,
        _,
    ):
        await project_repo.add(_project("project-1", status=UseStatus.COMPLETED))
        await proposal_repo.add(_project_proposal())

        response = await client.post(
            "/api/v1/collection-use-projects/project-1/publication-entries",
            json={"note": "External cannot write once completed"},
            headers={"X-Permission-Id": "permission-1"},
        )

    assert response.status_code == 403
    assert response.json()["error"] == "ACCESS_DENIED"


async def test_add_publication_entry_in_created_status_rejected() -> None:
    async with client_with_repos(caller=_CALLER) as (
        client,
        project_repo,
        proposal_repo,
        _,
    ):
        await project_repo.add(_project("project-1", status=UseStatus.CREATED))
        await proposal_repo.add(_project_proposal())

        response = await client.post(
            "/api/v1/collection-use-projects/project-1/publication-entries",
            json={"note": "No writes before the project starts"},
            headers={"X-Permission-Id": "permission-1"},
        )

    assert response.status_code == 409
    assert response.json()["error"] == "INVALID_TRANSITION"


async def test_edit_publication_entry_updates_note() -> None:
    async with client_with_repos(caller=_CALLER) as (
        client,
        project_repo,
        proposal_repo,
        _,
    ):
        await project_repo.add(_project("project-1", status=UseStatus.IN_PROGRESS))
        await proposal_repo.add(_project_proposal())
        created = await client.post(
            "/api/v1/collection-use-projects/project-1/publication-entries",
            json={"note": "original"},
            headers={"X-Permission-Id": "permission-1"},
        )
        entry_id = created.json()["id"]

        edited = await client.patch(
            f"/api/v1/collection-use-projects/project-1/publication-entries/{entry_id}",
            json={"note": "corrected"},
            headers={"X-Permission-Id": "permission-1"},
        )

    assert edited.status_code == 200
    body = edited.json()
    assert body["id"] == entry_id
    assert body["note"] == "corrected"
    assert body["addedBy"]["permissionId"] == "permission-1"


async def test_delete_publication_entry_removes_entry_and_attachments() -> None:
    storage = InMemoryFileStorage()
    async with client_with_repos(caller=_CALLER, file_storage=storage) as (
        client,
        project_repo,
        proposal_repo,
        _,
    ):
        await project_repo.add(_project("project-1", status=UseStatus.IN_PROGRESS))
        await proposal_repo.add(_project_proposal())
        created = await client.post(
            "/api/v1/collection-use-projects/project-1/publication-entries",
            json={"note": "entry to delete"},
            headers={"X-Permission-Id": "permission-1"},
        )
        entry_id = created.json()["id"]
        uploaded = await client.post(
            f"/api/v1/collection-use-projects/project-1/publication-entries/{entry_id}/attachments",
            files={"file": ("paper.pdf", b"%PDF-1.4 paper", "application/pdf")},
            data={
                "mediaType": "DOCUMENT",
                "attachmentDescription": "Publication document",
            },
            headers={"X-Permission-Id": "permission-1"},
        )
        file_reference = uploaded.json()["fileReference"]

        deleted = await client.delete(
            f"/api/v1/collection-use-projects/project-1/publication-entries/{entry_id}",
            headers={"X-Permission-Id": "permission-1"},
        )
        listing = await client.get(
            "/api/v1/collection-use-projects/project-1/publication-entries",
            headers={"X-Permission-Id": "permission-1"},
        )

    assert deleted.status_code == 204
    assert listing.status_code == 200
    assert listing.json()["content"] == []
    assert file_reference not in storage.files


async def test_delete_publication_entry_returns_404_for_another_project() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        project_repo,
        _,
        _,
    ):
        await project_repo.add(_project("project-1", status=UseStatus.COMPLETED))
        await project_repo.add(_project("project-2", status=UseStatus.COMPLETED))
        created = await client.post(
            "/api/v1/collection-use-projects/project-1/publication-entries",
            json={"note": "belongs to project one"},
            headers={"X-Permission-Id": "permission-staff"},
        )

        deleted = await client.delete(
            "/api/v1/collection-use-projects/project-2/publication-entries/"
            f"{created.json()['id']}",
            headers={"X-Permission-Id": "permission-staff"},
        )

    assert deleted.status_code == 404
    assert deleted.json()["error"] == "ENTRY_NOT_FOUND"


async def test_delete_confirmed_scientific_return_entry_is_blocked() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        project_repo,
        _,
        _,
    ):
        await project_repo.add(_project("project-1", status=UseStatus.COMPLETED))
        created = await client.post(
            "/api/v1/collection-use-projects/project-1/publication-entries",
            json={"note": "confirmed scientific return"},
            headers={"X-Permission-Id": "permission-staff"},
        )
        entry_id = created.json()["id"]
        publication_repo = app.dependency_overrides[get_publication_log_repo]()
        publication_repo.entries_in_use.add(entry_id)

        deleted = await client.delete(
            f"/api/v1/collection-use-projects/project-1/publication-entries/{entry_id}",
            headers={"X-Permission-Id": "permission-staff"},
        )

    assert deleted.status_code == 409
    assert deleted.json()["error"] == "PUBLICATION_ENTRY_IN_USE"


async def test_publication_entry_attachment_upload_and_download() -> None:
    async with client_with_repos(caller=_CALLER) as (
        client,
        project_repo,
        proposal_repo,
        _,
    ):
        await project_repo.add(_project("project-1", status=UseStatus.IN_PROGRESS))
        await proposal_repo.add(_project_proposal())
        created = await client.post(
            "/api/v1/collection-use-projects/project-1/publication-entries",
            json={"note": "with attachment"},
            headers={"X-Permission-Id": "permission-1"},
        )
        entry_id = created.json()["id"]
        uploaded = await client.post(
            f"/api/v1/collection-use-projects/project-1/publication-entries/{entry_id}/attachments",
            files={"file": ("paper.pdf", b"%PDF-1.4 paper", "application/pdf")},
            data={
                "mediaType": "DOCUMENT",
                "attachmentDescription": "The publication itself",
            },
            headers={"X-Permission-Id": "permission-1"},
        )
        assert uploaded.status_code == 201
        file_reference = uploaded.json()["fileReference"]

        download = await client.get(
            f"/api/v1/collection-use-projects/project-1/publication-entries/{entry_id}/attachments/{file_reference}",
            headers={"X-Permission-Id": "permission-1"},
        )

    assert download.status_code == 200
    assert download.content == b"%PDF-1.4 paper"
    assert "paper.pdf" in download.headers["content-disposition"]


async def test_publication_entry_attachment_requires_description() -> None:
    async with client_with_repos(caller=_CALLER) as (
        client,
        project_repo,
        proposal_repo,
        _,
    ):
        await project_repo.add(_project("project-1", status=UseStatus.IN_PROGRESS))
        await proposal_repo.add(_project_proposal())
        created = await client.post(
            "/api/v1/collection-use-projects/project-1/publication-entries",
            json={"note": "with attachment"},
            headers={"X-Permission-Id": "permission-1"},
        )
        entry_id = created.json()["id"]

        without_description = await client.post(
            f"/api/v1/collection-use-projects/project-1/publication-entries/{entry_id}/attachments",
            files={"file": ("paper.pdf", b"%PDF-1.4 paper", "application/pdf")},
            data={"mediaType": "DOCUMENT"},
            headers={"X-Permission-Id": "permission-1"},
        )
        blank_description = await client.post(
            f"/api/v1/collection-use-projects/project-1/publication-entries/{entry_id}/attachments",
            files={"file": ("paper.pdf", b"%PDF-1.4 paper", "application/pdf")},
            data={"mediaType": "DOCUMENT", "attachmentDescription": "   "},
            headers={"X-Permission-Id": "permission-1"},
        )

    assert without_description.status_code == 422
    assert blank_description.status_code == 422
    assert blank_description.json()["error"] == "VALIDATION_ERROR"


async def test_delete_publication_entry_attachment_removes_file() -> None:
    async with client_with_repos(caller=_CALLER) as (
        client,
        project_repo,
        proposal_repo,
        _,
    ):
        await project_repo.add(_project("project-1", status=UseStatus.IN_PROGRESS))
        await proposal_repo.add(_project_proposal())
        created = await client.post(
            "/api/v1/collection-use-projects/project-1/publication-entries",
            json={"note": "with attachment"},
            headers={"X-Permission-Id": "permission-1"},
        )
        entry_id = created.json()["id"]
        uploaded = await client.post(
            f"/api/v1/collection-use-projects/project-1/publication-entries/{entry_id}/attachments",
            files={"file": ("paper.pdf", b"%PDF-1.4 paper", "application/pdf")},
            data={
                "mediaType": "DOCUMENT",
                "attachmentDescription": "The publication itself",
            },
            headers={"X-Permission-Id": "permission-1"},
        )
        file_reference = uploaded.json()["fileReference"]

        deleted = await client.delete(
            f"/api/v1/collection-use-projects/project-1/publication-entries/{entry_id}/attachments/{file_reference}",
            headers={"X-Permission-Id": "permission-1"},
        )
        download = await client.get(
            f"/api/v1/collection-use-projects/project-1/publication-entries/{entry_id}/attachments/{file_reference}",
            headers={"X-Permission-Id": "permission-1"},
        )

    assert deleted.status_code == 204
    assert download.status_code == 404
    assert download.json()["error"] == "ATTACHMENT_NOT_FOUND"


async def test_get_publication_log_returns_404_without_entries() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        project_repo,
        _,
        _,
    ):
        await project_repo.add(_project("project-1", status=UseStatus.IN_PROGRESS))

        response = await client.get(
            "/api/v1/collection-use-projects/project-1/publication-log",
            headers={"X-Permission-Id": "permission-staff"},
        )

    assert response.status_code == 404
    assert response.json()["error"] == "PUBLICATION_LOG_NOT_FOUND"


async def _seed_publication_log_for_document(
    project_repo: InMemoryProjectRepository,
) -> None:
    linked_object = _collection_use_object("cuo-1", "INV-001")
    linked_object.display_title = "Tursiops truncatus"
    linked_object.collection_name = "Zoologia"
    await project_repo.add(
        _project(
            "project-1",
            status=UseStatus.COMPLETED,
            objects=[linked_object],
        )
    )
    publication_repo: InMemoryPublicationLogRepository = app.dependency_overrides[
        get_publication_log_repo
    ]()
    await publication_repo.add(
        PublicationLog(
            id=PublicationLogId("publication-log-1"),
            reference_number=ReferenceNumber("PUB-MUHNAC/COL/2026/0001"),
            collection_use_project_id=CollectionUseProjectId("project-1"),
            curator=PermissionId("permission-staff"),
        )
    )
    # Deliberately newest first: the register must read chronologically and must
    # include records beyond the UI's default 20-row page.
    for index in range(21, 0, -1):
        await publication_repo.save_entry(
            PublicationLogEntry(
                id=PublicationLogEntryId(f"publication-entry-{index}"),
                publication_log_id=PublicationLogId("publication-log-1"),
                added_at=datetime(2026, 6, index, tzinfo=UTC),
                added_by=PermissionId("permission-1"),
                note=f"Publication {index}",
                collection_use_object_id=(
                    CollectionUseObjectId("cuo-1") if index == 1 else None
                ),
                attachments=(
                    [
                        Attachment(
                            file_reference="publications/paper.pdf",
                            file_name="paper.pdf",
                            media_type=MediaType.DOCUMENT,
                            uploaded_at=datetime(2026, 6, 1, tzinfo=UTC),
                            description="Artigo aceite",
                        )
                    ]
                    if index == 1
                    else []
                ),
            )
        )


async def test_download_publication_log_document_fills_the_complete_rrp() -> None:
    async with client_with_repos(
        caller=_STAFF_CALLER,
        permission_records={
            "permission-1": _permission_record(
                "permission-1",
                GroupName.EXTERNAL,
                user_name="Ana Silva",
            ),
            "permission-staff": _permission_record(
                "permission-staff",
                GroupName.CURATORIAL,
                user_name="Nuno Curador",
            ),
        },
    ) as (client, project_repo, _, _):
        await _seed_publication_log_for_document(project_repo)

        response = await client.get(
            "/api/v1/collection-use-projects/project-1/publication-log/document",
            headers={"X-Permission-Id": "permission-staff"},
        )

    assert response.status_code == 200
    assert response.headers["content-type"] == DOCX_MEDIA_TYPE
    assert (
        "PUB-MUHNAC-COL-2026-0001-RRP.docx"
        in response.headers["content-disposition"]
    )

    document = DocxDocument(io.BytesIO(response.content))
    assert document.tables[0].rows[2].cells[0].text == "PUB-MUHNAC/COL/2026/0001"
    identification = {
        row.cells[0].text.split("\n")[0]: row.cells[1].text
        for row in document.tables[1].rows
    }
    assert identification["Requerente"] == "Ana Silva"
    assert identification["Curador"] == "Nuno Curador"
    assert identification["N.º de registos"] == "21"

    rows = document.tables[2].rows[1:]
    assert len(rows) == 21
    assert [row.cells[3].text for row in rows] == [
        f"Publication {index}" for index in range(1, 22)
    ]
    assert rows[0].cells[4].text == "INV-001 — Tursiops truncatus\nZoologia"
    assert rows[0].cells[5].text == "paper.pdf — Artigo aceite"


async def test_download_publication_log_document_returns_404_without_log() -> None:
    async with client_with_repos(caller=_STAFF_CALLER) as (
        client,
        project_repo,
        _,
        _,
    ):
        await project_repo.add(_project("project-1", status=UseStatus.COMPLETED))

        response = await client.get(
            "/api/v1/collection-use-projects/project-1/publication-log/document",
            headers={"X-Permission-Id": "permission-staff"},
        )

    assert response.status_code == 404
    assert response.json()["error"] == "PUBLICATION_LOG_NOT_FOUND"
