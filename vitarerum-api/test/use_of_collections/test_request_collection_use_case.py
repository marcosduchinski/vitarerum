from datetime import UTC, date, datetime

import pytest

from app.identity.public import Actor, GroupName, PermissionId
from app.use_of_collections.application.use_cases import (
    AddLogEntryAttachment,
    AddLogEntryAttachmentInput,
    AddObjectLogEntry,
    AddObjectLogEntryInput,
    AddObjectOccurrenceEntry,
    AddObjectOccurrenceEntryInput,
    AddOccurrenceEntryAttachment,
    AddOccurrenceEntryAttachmentInput,
    ApproveProposal,
    ApproveProposalInput,
    RejectProposal,
    RejectProposalInput,
    SendMessage,
    SendMessageInput,
    StartProject,
    StartProjectInput,
    SubmitProposal,
    SubmitProposalInput,
)
from app.use_of_collections.domain.enums import (
    ProposalEventType,
    ProposalStatus,
    UseEventType,
    UseStatus,
    UseType,
)
from app.use_of_collections.domain.models import (
    CollectionUseProject,
    CollectionUseProjectId,
    Conversation,
    ConversationId,
    EmailAddress,
    IntendedUse,
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
    ProposalId,
    ReferenceNumber,
    RequestedObject,
    RequestedObjectId,
)


class InMemoryCollectionUseProjectRepository:
    def __init__(self) -> None:
        self.items: dict[str, CollectionUseProject] = {}

    async def add(self, project: CollectionUseProject) -> None:
        self.items[project.id] = project

    async def get_by_id(self, project_id: str) -> CollectionUseProject | None:
        return self.items.get(project_id)

    async def get_by_reference(
        self, reference_number: ReferenceNumber
    ) -> CollectionUseProject | None:
        return next(
            (p for p in self.items.values() if p.reference_number == reference_number),
            None,
        )

    async def save(self, project: CollectionUseProject) -> None:
        self.items[project.id] = project

    async def list(self, filters, page, size):
        items = list(self.items.values())
        return items[page * size : page * size + size], len(items)


class InMemoryProposalRepository:
    def __init__(self) -> None:
        self.items: dict[str, Proposal] = {}

    async def add(self, proposal: Proposal) -> None:
        self.items[proposal.id] = proposal

    async def next_reference_number_for(self, day: date) -> ReferenceNumber:
        prefix = f"VRP-{day:%Y%m%d}-"
        latest = max(
            (
                item.reference_number.value
                for item in self.items.values()
                if item.reference_number.value.startswith(prefix)
            ),
            default=None,
        )
        sequence = int(latest.removeprefix(prefix)) + 1 if latest else 1
        return ReferenceNumber(f"{prefix}{sequence:04d}")

    async def get_by_id(self, proposal_id: ProposalId) -> Proposal | None:
        return self.items.get(proposal_id)

    async def get_by_project_id(self, project_id) -> Proposal | None:
        return next(
            (
                p
                for p in self.items.values()
                if p.collection_use_project_id == project_id
            ),
            None,
        )

    async def save(self, proposal: Proposal) -> None:
        self.items[proposal.id] = proposal

    async def list(self, filters, page, size):
        items = list(self.items.values())
        return items[page * size : page * size + size], len(items)


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
        return next(
            (
                log
                for log in self.items.values()
                if log.collection_use_project_id == project_id
            ),
            None,
        )

    async def get_entry_by_id(self, entry_id) -> ObjectLogEntry | None:
        return self.entries.get(entry_id)

    async def save(self, access_log: ObjectAccessLog) -> None:
        self.items[access_log.id] = access_log

    async def save_entry(self, entry: ObjectLogEntry) -> None:
        self.entries[entry.id] = entry

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
        ]
        return items[page * size : page * size + size], len(items)


class InMemoryOccurrenceLogRepository:
    def __init__(self) -> None:
        self.items: dict[str, ObjectOccurrenceLog] = {}
        self.entries: dict[str, ObjectOccurrenceEntry] = {}

    async def add(self, occurrence_log: ObjectOccurrenceLog) -> None:
        self.items[occurrence_log.id] = occurrence_log

    async def get_by_id(self, occurrence_log_id) -> ObjectOccurrenceLog | None:
        return self.items.get(occurrence_log_id)

    async def get_by_project_id(self, project_id) -> ObjectOccurrenceLog | None:
        return next(
            (
                log
                for log in self.items.values()
                if log.collection_use_project_id == project_id
            ),
            None,
        )

    async def get_entry_by_id(self, entry_id) -> ObjectOccurrenceEntry | None:
        return self.entries.get(entry_id)

    async def save(self, occurrence_log: ObjectOccurrenceLog) -> None:
        self.items[occurrence_log.id] = occurrence_log

    async def save_entry(self, entry: ObjectOccurrenceEntry) -> None:
        self.entries[entry.id] = entry

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
        ]
        return items[page * size : page * size + size], len(items)


class RecordingFileStorage:
    def __init__(self) -> None:
        self.saved: list[tuple[bytes, str]] = []

    async def save(self, content: bytes, filename: str) -> str:
        self.saved.append((content, filename))
        return f"uploads/{filename}"


def _make_caller(email: str = "alice@example.org") -> Actor:
    return Actor(
        id=PermissionId("permission-1"),
        group=GroupName.EXTERNAL,
        email=email,
    )


def _make_curator() -> Actor:
    return Actor(
        id=PermissionId("permission-2"),
        group=GroupName.CURATORIAL,
        email="bob@museum.pt",
    )


def _make_project(status: UseStatus = UseStatus.IN_PROGRESS) -> CollectionUseProject:
    return CollectionUseProject(
        id=CollectionUseProjectId("project-1"),
        reference_number=ReferenceNumber("CUP-LOG00001"),
        title="Collection study",
        purpose="To study the collection",
        intended_use=IntendedUse(use_type=UseType.IN_SITU_VISIT),
        status=status,
        begin_date=date(2026, 6, 1),
        end_date=date(2026, 6, 7),
        requested_by=PermissionId("permission-1"),
    )


async def test_submit_proposal_persists_proposal_and_conversation() -> None:
    proposal_repository = InMemoryProposalRepository()
    conversation_repository = InMemoryConversationRepository()
    use_case = SubmitProposal(
        proposal_repository=proposal_repository,
        conversation_repository=conversation_repository,
    )

    result = await use_case.execute(
        SubmitProposalInput(
            title="Collection study",
            intended_use=IntendedUse(use_type=UseType.IN_SITU_VISIT),
            purpose="To study the collection",
            begin_date=date(2026, 6, 1),
            end_date=date(2026, 6, 7),
            requested_by=_make_caller(),
        )
    )

    assert result.proposal.status == ProposalStatus.SUBMITTED

    saved_proposal = await proposal_repository.get_by_id(result.proposal.id)
    assert saved_proposal is not None
    assert saved_proposal.status == ProposalStatus.SUBMITTED
    assert saved_proposal.intended_use.use_type == UseType.IN_SITU_VISIT
    assert saved_proposal.title == "Collection study"
    assert saved_proposal.begin_date == date(2026, 6, 1)
    assert saved_proposal.end_date == date(2026, 6, 7)
    assert saved_proposal.reference_number.value.startswith("VRP-")
    assert saved_proposal.reference_number.value.endswith("-0001")
    assert saved_proposal.events[0].type == ProposalEventType.SUBMITTED
    assert saved_proposal.events[0].triggered_by == "permission-1"

    saved_conv = await conversation_repository.get_by_proposal_id(result.proposal.id)
    assert saved_conv is not None
    assert saved_conv.proposal_id == result.proposal.id


async def test_submit_proposal_accepts_other_use_type() -> None:
    proposal_repository = InMemoryProposalRepository()
    conversation_repository = InMemoryConversationRepository()
    use_case = SubmitProposal(
        proposal_repository=proposal_repository,
        conversation_repository=conversation_repository,
    )

    result = await use_case.execute(
        SubmitProposalInput(
            title="Unclassified use",
            intended_use=IntendedUse(use_type=UseType.OTHER),
            purpose="Other purpose",
            begin_date=date(2026, 6, 1),
            end_date=date(2026, 6, 7),
            requested_by=_make_caller(),
        )
    )

    saved_proposal = await proposal_repository.get_by_id(result.proposal.id)
    assert saved_proposal is not None
    assert saved_proposal.intended_use.use_type == UseType.OTHER


async def test_submit_proposal_generates_daily_sequential_reference_number() -> None:
    proposal_repository = InMemoryProposalRepository()
    conversation_repository = InMemoryConversationRepository()
    use_case = SubmitProposal(
        proposal_repository=proposal_repository,
        conversation_repository=conversation_repository,
    )

    first = await use_case.execute(
        SubmitProposalInput(
            title="Collection study",
            intended_use=IntendedUse(use_type=UseType.IN_SITU_VISIT),
            purpose="To study the collection",
            begin_date=date(2026, 6, 1),
            end_date=date(2026, 6, 7),
            requested_by=_make_caller(),
        )
    )
    second = await use_case.execute(
        SubmitProposalInput(
            title="Collection study 2",
            intended_use=IntendedUse(use_type=UseType.IN_SITU_VISIT),
            purpose="To study the collection again",
            begin_date=date(2026, 6, 1),
            end_date=date(2026, 6, 7),
            requested_by=_make_caller(),
        )
    )

    day = first.proposal.submitted_at.strftime("%Y%m%d")
    assert first.proposal.reference_number == ReferenceNumber(f"VRP-{day}-0001")
    assert second.proposal.reference_number == ReferenceNumber(f"VRP-{day}-0002")


async def test_submit_proposal_uses_valid_sender_fallback_without_user_email() -> None:
    proposal_repository = InMemoryProposalRepository()
    conversation_repository = InMemoryConversationRepository()
    caller = _make_caller(email="")
    use_case = SubmitProposal(
        proposal_repository=proposal_repository,
        conversation_repository=conversation_repository,
    )

    result = await use_case.execute(
        SubmitProposalInput(
            title="Collection study",
            intended_use=IntendedUse(use_type=UseType.IN_SITU_VISIT),
            purpose="To study the collection",
            begin_date=date(2026, 6, 1),
            end_date=date(2026, 6, 7),
            requested_by=caller,
        )
    )

    saved_conv = await conversation_repository.get_by_proposal_id(result.proposal.id)
    assert saved_conv is not None
    assert saved_conv.messages[0].sender.value == "permission-1@unknown.local"


def _make_curator() -> Actor:
    return Actor(
        id=PermissionId("curator-1"),
        group=GroupName.CURATORIAL,
        email="bob@museum.pt",
    )


async def test_approve_proposal_creates_requested_project() -> None:
    proposal_repository = InMemoryProposalRepository()
    project_repository = InMemoryCollectionUseProjectRepository()
    proposal = Proposal(
        id=ProposalId("proposal-1"),
        reference_number=ReferenceNumber("VRP-20260601-0001"),
        title="Proposal title",
        collection_use_project_id="project-1",
        intended_use=IntendedUse(use_type=UseType.IN_SITU_VISIT),
        begin_date=date(2026, 6, 1),
        end_date=date(2026, 6, 7),
        status=ProposalStatus.PENDING,
        requested_by=PermissionId("permission-1"),
        submitted_at=datetime(2026, 6, 1, tzinfo=UTC),
    )
    await proposal_repository.add(proposal)

    use_case = ApproveProposal(proposal_repository, project_repository)
    result = await use_case.execute(
        ApproveProposalInput(
            proposal_id=ProposalId("proposal-1"),
            caller=_make_curator(),
            title="Collection study",
            purpose="To study the collection",
            begin_date=date(2026, 7, 1),
            end_date=date(2026, 7, 7),
            note="approved",
        )
    )

    assert result.proposal.status == ProposalStatus.APPROVED
    assert result.project.status == UseStatus.CREATED
    assert result.project.intended_use.use_type == UseType.IN_SITU_VISIT
    assert result.project.reference_number.value.startswith("CUP-")

    saved_project = await project_repository.get_by_id("project-1")
    assert saved_project is not None
    assert saved_project.status == UseStatus.CREATED
    assert saved_project.title == "Collection study"
    assert saved_project.proposal_id == "proposal-1"
    assert saved_project.events[0].type == UseEventType.REQUESTED
    assert saved_project.events[0].triggered_by == "curator-1"


async def test_reject_proposal_sends_reason_message_to_requester() -> None:
    proposal_repository = InMemoryProposalRepository()
    conversation_repository = InMemoryConversationRepository()
    proposal = Proposal(
        id=ProposalId("proposal-1"),
        reference_number=ReferenceNumber("VRP-20260601-0001"),
        title="Proposal title",
        collection_use_project_id="project-1",
        intended_use=IntendedUse(use_type=UseType.IN_SITU_VISIT),
        begin_date=date(2026, 6, 1),
        end_date=date(2026, 6, 7),
        status=ProposalStatus.PENDING,
        requested_by=PermissionId("permission-1"),
        submitted_at=datetime(2026, 6, 1, tzinfo=UTC),
    )
    await proposal_repository.add(proposal)
    await conversation_repository.add(
        Conversation.start(
            id=ConversationId("conversation-1"),
            proposal_id=proposal.id,
            initial_message=Message(
                id=MessageId("message-1"),
                sent_at=datetime(2026, 6, 1, tzinfo=UTC),
                sender=EmailAddress("alice@example.org"),
                recipient=EmailAddress("collections@museum.pt"),
                subject="Initial",
                body="Initial message",
            ),
        )
    )

    result = await RejectProposal(
        proposal_repository=proposal_repository,
        conversation_repository=conversation_repository,
    ).execute(
        RejectProposalInput(
            proposal_id=proposal.id,
            caller=_make_curator(),
            reason="The request is outside the collection policy.",
            requester_email="alice@example.org",
        )
    )

    saved_conversation = await conversation_repository.get_by_proposal_id(proposal.id)
    assert result.proposal.status == ProposalStatus.REJECTED
    assert saved_conversation is not None
    rejection_message = saved_conversation.messages[-1]
    assert rejection_message.sender.value == "bob@museum.pt"
    assert rejection_message.recipient.value == "alice@example.org"
    assert rejection_message.subject == "Proposal rejected: VRP-20260601-0001"
    assert rejection_message.body == "The request is outside the collection policy."


async def test_send_message_uses_valid_sender_fallback_without_user_email() -> None:
    proposal_repository = InMemoryProposalRepository()
    conversation_repository = InMemoryConversationRepository()
    caller = _make_caller(email="")
    proposal = Proposal(
        id=ProposalId("proposal-1"),
        reference_number=ReferenceNumber("VRP-20260601-0001"),
        title="Proposal title",
        collection_use_project_id="project-1",
        intended_use=IntendedUse(use_type=UseType.IN_SITU_VISIT),
        begin_date=date(2026, 6, 1),
        end_date=date(2026, 6, 7),
        status=ProposalStatus.PENDING,
        requested_by=caller.id,
        submitted_at=datetime(2026, 6, 1, tzinfo=UTC),
    )
    await proposal_repository.add(proposal)
    await conversation_repository.add(
        Conversation.start(
            id=ConversationId("conversation-1"),
            proposal_id=proposal.id,
            initial_message=Message(
                id=MessageId("message-1"),
                sent_at=datetime(2026, 6, 1, tzinfo=UTC),
                sender=EmailAddress("alice@example.org"),
                recipient=EmailAddress("collections@museum.pt"),
                subject="Initial",
                body="Initial message",
            ),
        )
    )

    message = await SendMessage(
        proposal_repository=proposal_repository,
        conversation_repository=conversation_repository,
    ).execute(
        SendMessageInput(
            proposal_id=proposal.id,
            caller=caller,
            recipient="collections@museum.pt",
            subject="Follow-up",
            body="More details",
        )
    )

    assert message.sender.value == "permission-1@unknown.local"


async def test_log_entry_attachment_invalid_media_type_does_not_save_file() -> None:
    project_repository = InMemoryCollectionUseProjectRepository()
    access_log_repository = InMemoryAccessLogRepository()
    storage = RecordingFileStorage()
    project = _make_project()
    await project_repository.add(project)
    access_log = ObjectAccessLog(
        id=ObjectAccessLogId("log-1"),
        reference_number=ReferenceNumber("OAL-12345678"),
        collection_use_project_id=project.id,
    )
    entry = ObjectLogEntry(
        id=ObjectLogEntryId("entry-1"),
        object_access_log_id=access_log.id,
        requested_object_id=RequestedObjectId("req-1"),
        number_of_objects=1,
        added_at=datetime(2026, 6, 1, tzinfo=UTC),
        added_by=PermissionId("permission-1"),
    )
    await access_log_repository.add(access_log)
    await access_log_repository.save_entry(entry)

    with pytest.raises(ValueError):
        await AddLogEntryAttachment(
            project_repository, access_log_repository, storage
        ).execute(
            AddLogEntryAttachmentInput(
                project_id=project.id,
                entry_id=entry.id,
                caller=_make_caller(),
                file_content=b"invalid",
                file_name="upload.bin",
                media_type="NOT_A_MEDIA_TYPE",
            )
        )

    assert storage.saved == []
    assert entry.attachments == []


async def test_add_object_log_entry_creates_access_log_on_first_entry() -> None:
    project_repository = InMemoryCollectionUseProjectRepository()
    access_log_repository = InMemoryAccessLogRepository()
    proposal_repository = InMemoryProposalRepository()
    project = _make_project()
    await project_repository.add(project)
    await proposal_repository.add(
        _proposal_with_requested_object(extra_objects=[("req-2", "INV-002")])
    )

    entry = await AddObjectLogEntry(
        project_repository, access_log_repository, proposal_repository
    ).execute(
        AddObjectLogEntryInput(
            project_id=project.id,
            caller=_make_caller(),
            requested_object_id=RequestedObjectId("req-1"),
            number_of_objects=2,
            observations="Handled with gloves",
        )
    )

    access_log = await access_log_repository.get_by_project_id(project.id)
    assert access_log is not None
    assert access_log.reference_number.value.startswith("OAL-")
    assert access_log.date_conclusion is None
    assert access_log.curator is None
    assert entry.object_access_log_id == access_log.id
    assert entry.requested_object_id == "req-1"
    assert entry.number_of_objects == 2
    assert entry.observations == "Handled with gloves"

    await AddObjectLogEntry(
        project_repository, access_log_repository, proposal_repository
    ).execute(
        AddObjectLogEntryInput(
            project_id=project.id,
            caller=_make_caller(),
            requested_object_id=RequestedObjectId("req-2"),
            number_of_objects=1,
        )
    )
    assert len(access_log_repository.items) == 1


def _proposal_with_requested_object(
    inventory_number: str = "INV-001",
    requested_object_id: str = "req-1",
    extra_objects: list[tuple[str, str]] | None = None,
) -> Proposal:
    """Approved proposal carrying one (or more) requested objects.

    ``extra_objects`` is a list of ``(requested_object_id, inventory_number)``
    tuples for tests that add several journal entries."""
    objects = [(requested_object_id, inventory_number), *(extra_objects or [])]
    return Proposal(
        id=ProposalId("proposal-1"),
        reference_number=ReferenceNumber("VRP-20260601-0001"),
        title="Proposal title",
        collection_use_project_id=CollectionUseProjectId("project-1"),
        intended_use=IntendedUse(use_type=UseType.IN_SITU_VISIT),
        begin_date=date(2026, 6, 1),
        end_date=date(2026, 6, 7),
        status=ProposalStatus.APPROVED,
        requested_by=PermissionId("permission-1"),
        submitted_at=datetime(2026, 6, 1, tzinfo=UTC),
        requested_objects=[
            RequestedObject(
                id=RequestedObjectId(rid),
                inventory_number=inv,
                category="fox head",
                description="a fox head",
                requested_at=datetime(2026, 6, 1, tzinfo=UTC),
                requested_by=PermissionId("permission-1"),
            )
            for rid, inv in objects
        ],
    )


async def test_start_project_seeds_access_log_from_requested_objects() -> None:
    project_repository = InMemoryCollectionUseProjectRepository()
    proposal_repository = InMemoryProposalRepository()
    access_log_repository = InMemoryAccessLogRepository()
    await project_repository.add(_make_project(status=UseStatus.CREATED))
    await proposal_repository.add(_proposal_with_requested_object())

    project = await StartProject(
        project_repository, proposal_repository, access_log_repository
    ).execute(
        StartProjectInput(
            project_id=CollectionUseProjectId("project-1"),
            caller=_make_curator(),
        )
    )

    assert project.status == UseStatus.IN_PROGRESS
    access_log = await access_log_repository.get_by_project_id(
        CollectionUseProjectId("project-1")
    )
    assert access_log is not None
    assert access_log.reference_number.value.startswith("OAL-")

    entries, total = await access_log_repository.list_entries_by_project(
        CollectionUseProjectId("project-1"), None, 0, 10
    )
    assert total == 1
    entry = entries[0]
    # The entry links back to the requested object, with quantity defaulting to
    # 1 and the curator recorded as addedBy.
    assert entry.requested_object_id == RequestedObjectId("req-1")
    assert entry.number_of_objects == 1
    assert entry.added_by == PermissionId("curator-1")


async def test_start_project_without_requested_objects_creates_no_access_log() -> None:
    project_repository = InMemoryCollectionUseProjectRepository()
    proposal_repository = InMemoryProposalRepository()
    access_log_repository = InMemoryAccessLogRepository()
    await project_repository.add(_make_project(status=UseStatus.CREATED))
    proposal = _proposal_with_requested_object()
    proposal.requested_objects = []
    await proposal_repository.add(proposal)

    await StartProject(
        project_repository, proposal_repository, access_log_repository
    ).execute(
        StartProjectInput(
            project_id=CollectionUseProjectId("project-1"),
            caller=_make_curator(),
        )
    )

    # Nothing requested → the log stays lazily uncreated.
    access_log = await access_log_repository.get_by_project_id(
        CollectionUseProjectId("project-1")
    )
    assert access_log is None


async def test_log_entry_links_to_requested_object() -> None:
    project_repository = InMemoryCollectionUseProjectRepository()
    access_log_repository = InMemoryAccessLogRepository()
    proposal_repository = InMemoryProposalRepository()
    await project_repository.add(_make_project())
    await proposal_repository.add(_proposal_with_requested_object())

    entry = await AddObjectLogEntry(
        project_repository, access_log_repository, proposal_repository
    ).execute(
        AddObjectLogEntryInput(
            project_id=CollectionUseProjectId("project-1"),
            caller=_make_caller(),
            requested_object_id=RequestedObjectId("req-1"),
            number_of_objects=1,
        )
    )

    assert entry.requested_object_id == "req-1"


async def test_log_entry_rejects_unknown_requested_object() -> None:
    project_repository = InMemoryCollectionUseProjectRepository()
    access_log_repository = InMemoryAccessLogRepository()
    proposal_repository = InMemoryProposalRepository()
    await project_repository.add(_make_project())
    await proposal_repository.add(_proposal_with_requested_object())

    with pytest.raises(ValueError, match="not part of this project"):
        await AddObjectLogEntry(
            project_repository,
            access_log_repository,
            proposal_repository,
        ).execute(
            AddObjectLogEntryInput(
                project_id=CollectionUseProjectId("project-1"),
                caller=_make_caller(),
                requested_object_id=RequestedObjectId("does-not-exist"),
                number_of_objects=1,
            )
        )
    # the failed link must not have created an entry or a log
    assert access_log_repository.entries == {}


async def test_occurrence_entry_links_to_requested_object() -> None:
    project_repository = InMemoryCollectionUseProjectRepository()
    occurrence_log_repository = InMemoryOccurrenceLogRepository()
    proposal_repository = InMemoryProposalRepository()
    await project_repository.add(_make_project())
    await proposal_repository.add(_proposal_with_requested_object())

    entry = await AddObjectOccurrenceEntry(
        project_repository,
        occurrence_log_repository,
        proposal_repository,
    ).execute(
        AddObjectOccurrenceEntryInput(
            project_id=CollectionUseProjectId("project-1"),
            caller=_make_caller(),
            requested_object_id=RequestedObjectId("req-1"),
            number_of_objects=1,
            occurrence_date=datetime(2026, 6, 2, tzinfo=UTC),
            location="Conservation lab",
            detailed_description="Condition checked",
        )
    )

    assert entry.requested_object_id == "req-1"


async def test_object_log_entry_requires_at_least_one_object() -> None:
    with pytest.raises(ValueError):
        ObjectLogEntry(
            id=ObjectLogEntryId("entry-1"),
            object_access_log_id=ObjectAccessLogId("log-1"),
            requested_object_id=RequestedObjectId("req-1"),
            number_of_objects=0,
            added_at=datetime(2026, 6, 1, tzinfo=UTC),
            added_by=PermissionId("permission-1"),
        )


async def test_occurrence_attachment_invalid_media_type_does_not_save_file() -> None:
    project_repository = InMemoryCollectionUseProjectRepository()
    occurrence_log_repository = InMemoryOccurrenceLogRepository()
    storage = RecordingFileStorage()
    project = _make_project()
    await project_repository.add(project)
    occurrence_log = ObjectOccurrenceLog(
        id=ObjectOccurrenceLogId("log-1"),
        reference_number=ReferenceNumber("OOL-12345678"),
        collection_use_project_id=project.id,
    )
    entry = ObjectOccurrenceEntry(
        id=ObjectOccurrenceEntryId("occ-1"),
        object_occurrence_log_id=occurrence_log.id,
        requested_object_id=RequestedObjectId("req-1"),
        number_of_objects=1,
        occurrence_date=datetime(2026, 6, 1, tzinfo=UTC),
        location="Storage room",
        reported_by=PermissionId("permission-1"),
        detailed_description="Entry",
    )
    await occurrence_log_repository.add(occurrence_log)
    await occurrence_log_repository.save_entry(entry)

    with pytest.raises(ValueError):
        await AddOccurrenceEntryAttachment(
            project_repository, occurrence_log_repository, storage
        ).execute(
            AddOccurrenceEntryAttachmentInput(
                project_id=project.id,
                entry_id=entry.id,
                caller=_make_caller(),
                file_content=b"invalid",
                file_name="upload.bin",
                media_type="NOT_A_MEDIA_TYPE",
            )
        )

    assert storage.saved == []
    assert entry.attachments == []


async def test_add_occurrence_entry_creates_occurrence_log_on_first_entry() -> None:
    project_repository = InMemoryCollectionUseProjectRepository()
    occurrence_log_repository = InMemoryOccurrenceLogRepository()
    proposal_repository = InMemoryProposalRepository()
    project = _make_project()
    await project_repository.add(project)
    await proposal_repository.add(
        _proposal_with_requested_object(extra_objects=[("req-2", "INV-002")])
    )

    entry = await AddObjectOccurrenceEntry(
        project_repository, occurrence_log_repository, proposal_repository
    ).execute(
        AddObjectOccurrenceEntryInput(
            project_id=project.id,
            caller=_make_caller(),
            requested_object_id=RequestedObjectId("req-1"),
            number_of_objects=2,
            occurrence_date=datetime(2026, 6, 2, 11, 30, tzinfo=UTC),
            location="Conservation lab",
            detailed_description="Minor abrasion observed",
            testimonial="Reported by the conservator",
        )
    )

    occurrence_log = await occurrence_log_repository.get_by_project_id(project.id)
    assert occurrence_log is not None
    assert occurrence_log.reference_number.value.startswith("OOL-")
    assert occurrence_log.date_conclusion is None
    assert occurrence_log.curator is None
    assert entry.object_occurrence_log_id == occurrence_log.id
    assert entry.requested_object_id == "req-1"
    assert entry.number_of_objects == 2
    assert entry.occurrence_date == datetime(2026, 6, 2, 11, 30, tzinfo=UTC)
    assert entry.location == "Conservation lab"
    assert entry.reported_by == "permission-1"
    assert entry.detailed_description == "Minor abrasion observed"
    assert entry.testimonial == "Reported by the conservator"

    await AddObjectOccurrenceEntry(
        project_repository, occurrence_log_repository, proposal_repository
    ).execute(
        AddObjectOccurrenceEntryInput(
            project_id=project.id,
            caller=_make_caller(),
            requested_object_id=RequestedObjectId("req-2"),
            number_of_objects=1,
            occurrence_date=datetime(2026, 6, 3, tzinfo=UTC),
            location="Storage room",
            detailed_description="Routine check",
        )
    )
    assert len(occurrence_log_repository.items) == 1


async def test_occurrence_entry_validates_required_fields() -> None:
    def _entry(**overrides):
        kwargs = {
            "id": ObjectOccurrenceEntryId("occ-1"),
            "object_occurrence_log_id": ObjectOccurrenceLogId("log-1"),
            "requested_object_id": RequestedObjectId("req-1"),
            "number_of_objects": 1,
            "occurrence_date": datetime(2026, 6, 1, tzinfo=UTC),
            "location": "Storage room",
            "reported_by": PermissionId("permission-1"),
            "detailed_description": "Occurrence",
        }
        kwargs.update(overrides)
        return ObjectOccurrenceEntry(**kwargs)

    with pytest.raises(ValueError):
        _entry(number_of_objects=0)
    with pytest.raises(ValueError):
        _entry(location="")
    with pytest.raises(ValueError):
        _entry(detailed_description="")
