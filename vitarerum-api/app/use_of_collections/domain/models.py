from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import NewType

from app.shared.exceptions import (
    InsufficientGroup as InsufficientGroup,
)
from app.shared.kernel import (
    EMAIL_ADDRESS_PATTERN as EMAIL_ADDRESS_PATTERN,
)
from app.shared.kernel import (
    REFERENCE_NUMBER_PATTERN as REFERENCE_NUMBER_PATTERN,
)
from app.shared.kernel import (
    DocumentId as DocumentId,
)
from app.shared.kernel import (
    DocumentType as DocumentType,
)
from app.shared.kernel import (
    EmailAddress as EmailAddress,
)
from app.shared.kernel import (
    IntendedUse as IntendedUse,
)
from app.shared.kernel import (
    MessageAttachment as MessageAttachment,
)
from app.shared.kernel import (
    PermissionId as PermissionId,
)
from app.shared.kernel import (
    ReferenceNumber as ReferenceNumber,
)
from app.use_of_collections.domain.enums import (
    MediaType,
    ProposalEventType,
    ProposalStatus,
    UseEventType,
    UseResult,
    UseStatus,
)

CollectionUseProjectId = NewType("CollectionUseProjectId", str)
CollectionUseObjectId = NewType("CollectionUseObjectId", str)
ObjectAccessLogId = NewType("ObjectAccessLogId", str)
ObjectLogEntryId = NewType("ObjectLogEntryId", str)
ObjectOccurrenceLogId = NewType("ObjectOccurrenceLogId", str)
ObjectOccurrenceEntryId = NewType("ObjectOccurrenceEntryId", str)
PublicationLogId = NewType("PublicationLogId", str)
PublicationLogEntryId = NewType("PublicationLogEntryId", str)
ProposalId = NewType("ProposalId", str)
RequestedDocumentId = NewType("RequestedDocumentId", str)
RequestedObjectId = NewType("RequestedObjectId", str)
ConversationId = NewType("ConversationId", str)
MessageId = NewType("MessageId", str)

_PROPOSAL_TERMINAL_STATUSES = {
    ProposalStatus.APPROVED,
    ProposalStatus.REJECTED,
    ProposalStatus.CANCELLED,
}


class InvalidTransition(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Attachment:
    file_reference: str
    file_name: str
    media_type: MediaType
    uploaded_at: datetime
    note: str | None = None


@dataclass(frozen=True, slots=True)
class UseEvent:
    occurred_at: datetime
    type: UseEventType
    triggered_by: PermissionId
    note: str | None = None


@dataclass(slots=True)
class ObjectLogEntry:
    """Entity inside ObjectAccessLog — one accessed object with its quantity.

    The accessed object is identified through ``collection_use_object_id``, which
    points to a CollectionUseObject of the project (the project-owned copy that
    carries the object's inventory snapshot)."""

    id: ObjectLogEntryId
    object_access_log_id: ObjectAccessLogId
    collection_use_object_id: CollectionUseObjectId
    number_of_objects: int
    added_at: datetime
    added_by: PermissionId
    observations: str | None = None
    attachments: list[Attachment] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.number_of_objects < 1:
            raise ValueError("numberOfObjects must be at least 1.")

    def add_attachment(self, attachment: Attachment) -> None:
        self.attachments.append(attachment)

    def edit(
        self,
        *,
        added_at: datetime,
        number_of_objects: int,
        observations: str | None,
    ) -> None:
        if number_of_objects < 1:
            raise ValueError("numberOfObjects must be at least 1.")
        self.added_at = added_at
        self.number_of_objects = number_of_objects
        self.observations = observations


@dataclass(slots=True)
class ObjectAccessLog:
    """Journal aggregate — per-project register of accessed collection objects,
    concluded by a curator."""

    id: ObjectAccessLogId
    reference_number: ReferenceNumber
    collection_use_project_id: CollectionUseProjectId
    date_conclusion: datetime | None = None
    curator: PermissionId | None = None
    objects: list[ObjectLogEntry] = field(default_factory=list)

    @property
    def is_concluded(self) -> bool:
        return self.date_conclusion is not None

    def add_object_log_entry(self, entry: ObjectLogEntry) -> None:
        if self.is_concluded:
            raise InvalidTransition(
                "Cannot add entries to a concluded object access log"
            )
        if entry.object_access_log_id != self.id:
            raise ValueError("Entry does not belong to this object access log.")
        self.objects.append(entry)


@dataclass(slots=True)
class ObjectOccurrenceEntry:
    """Entity inside ObjectOccurrenceLog — one observed occurrence involving a
    collection object."""

    id: ObjectOccurrenceEntryId
    object_occurrence_log_id: ObjectOccurrenceLogId
    collection_use_object_id: CollectionUseObjectId
    number_of_objects: int
    occurrence_date: datetime
    location: str
    reported_by: PermissionId
    detailed_description: str
    testimonial: str | None = None
    attachments: list[Attachment] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.number_of_objects < 1:
            raise ValueError("numberOfObjects must be at least 1.")
        if not self.location:
            raise ValueError("location is required.")
        if not self.detailed_description:
            raise ValueError("detailedDescription is required.")

    def add_attachment(self, attachment: Attachment) -> None:
        self.attachments.append(attachment)

    def edit(
        self,
        *,
        number_of_objects: int,
        occurrence_date: datetime,
        location: str,
        detailed_description: str,
        testimonial: str | None,
    ) -> None:
        if number_of_objects < 1:
            raise ValueError("numberOfObjects must be at least 1.")
        if not location:
            raise ValueError("location is required.")
        if not detailed_description:
            raise ValueError("detailedDescription is required.")
        self.number_of_objects = number_of_objects
        self.occurrence_date = occurrence_date
        self.location = location
        self.detailed_description = detailed_description
        self.testimonial = testimonial


@dataclass(slots=True)
class ObjectOccurrenceLog:
    """Journal aggregate — per-project register of object occurrences,
    concluded by a curator."""

    id: ObjectOccurrenceLogId
    reference_number: ReferenceNumber
    collection_use_project_id: CollectionUseProjectId
    date_conclusion: datetime | None = None
    curator: PermissionId | None = None
    objects: list[ObjectOccurrenceEntry] = field(default_factory=list)

    @property
    def is_concluded(self) -> bool:
        return self.date_conclusion is not None

    def add_object_occurrence_entry(self, entry: ObjectOccurrenceEntry) -> None:
        if self.is_concluded:
            raise InvalidTransition(
                "Cannot add entries to a concluded object occurrence log"
            )
        if entry.object_occurrence_log_id != self.id:
            raise ValueError("Entry does not belong to this object occurrence log.")
        self.objects.append(entry)


@dataclass(slots=True)
class PublicationLogEntry:
    """Entity inside PublicationLog — one note about a publication or output
    derived from the project, with optional file attachments."""

    id: PublicationLogEntryId
    publication_log_id: PublicationLogId
    added_at: datetime
    added_by: PermissionId
    note: str
    attachments: list[Attachment] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.note:
            raise ValueError("note is required.")

    def add_attachment(self, attachment: Attachment) -> None:
        self.attachments.append(attachment)

    def edit(self, *, note: str) -> None:
        if not note:
            raise ValueError("note is required.")
        self.note = note


@dataclass(slots=True)
class PublicationLog:
    """Journal aggregate — per-project register of publications/outputs. The
    `curator` is informational (the staff member related to the project)."""

    id: PublicationLogId
    reference_number: ReferenceNumber
    collection_use_project_id: CollectionUseProjectId
    curator: PermissionId | None = None
    entries: list[PublicationLogEntry] = field(default_factory=list)

    def add_entry(self, entry: PublicationLogEntry) -> None:
        if entry.publication_log_id != self.id:
            raise ValueError("Entry does not belong to this publication log.")
        self.entries.append(entry)


@dataclass(slots=True)
class CollectionUseObject:
    """Project-owned copy of an object to be used, taken from the proposal's
    requested objects when the project is created.

    This is a clean clone of :class:`RequestedObject`: the project carries its own
    object snapshots so the Project Phase is self-contained and does not depend on
    the proposal at runtime (the proposal context may later live in a separate
    service). Journal entries reference these by ``CollectionUseObjectId``."""

    id: CollectionUseObjectId
    inventory_number: str
    category: str
    description: str
    requested_at: datetime
    requested_by: PermissionId
    display_title: str | None = None
    object_name: str | None = None
    brief_description_snapshot: str | None = None

    def __post_init__(self) -> None:
        if not self.inventory_number:
            raise ValueError("inventoryNumber is required.")


@dataclass(slots=True)
class CollectionUseProject:
    id: CollectionUseProjectId
    reference_number: ReferenceNumber
    title: str
    purpose: str
    intended_use: IntendedUse
    status: UseStatus
    begin_date: date
    end_date: date
    requested_by: PermissionId
    proposal_id: ProposalId | None = None
    request_note: str | None = None
    note: str | None = None
    result: UseResult | None = None
    authorised_by: PermissionId | None = None
    authorised_at: datetime | None = None
    events: list[UseEvent] = field(default_factory=list)
    objects: list[CollectionUseObject] = field(default_factory=list)

    def record_requested(
        self,
        occurred_at: datetime,
        triggered_by: PermissionId,
        note: str | None = None,
    ) -> None:
        self.status = UseStatus.CREATED
        self.events.append(
            UseEvent(
                occurred_at=occurred_at,
                type=UseEventType.REQUESTED,
                triggered_by=triggered_by,
                note=note,
            )
        )

    def record_started(
        self,
        occurred_at: datetime,
        triggered_by: PermissionId,
        note: str | None = None,
    ) -> None:
        if self.status != UseStatus.CREATED:
            raise InvalidTransition("Project must be in CREATED status to be started")
        self.status = UseStatus.IN_PROGRESS
        self.events.append(
            UseEvent(
                occurred_at=occurred_at,
                type=UseEventType.STARTED,
                triggered_by=triggered_by,
                note=note,
            )
        )

    def record_completed(
        self,
        occurred_at: datetime,
        triggered_by: PermissionId,
        note: str | None = None,
    ) -> None:
        if self.status != UseStatus.IN_PROGRESS:
            raise InvalidTransition("Only IN_PROGRESS projects can be concluded")
        self.status = UseStatus.COMPLETED
        self.result = UseResult.COMPLETED
        self.events.append(
            UseEvent(
                occurred_at=occurred_at,
                type=UseEventType.COMPLETED,
                triggered_by=triggered_by,
                note=note,
            )
        )

    def record_cancelled(
        self,
        occurred_at: datetime,
        triggered_by: PermissionId,
        reason: str,
    ) -> None:
        if self.status in {UseStatus.COMPLETED, UseStatus.CANCELLED}:
            raise InvalidTransition(
                "Cannot cancel a project that is already completed or cancelled"
            )
        self.status = UseStatus.CANCELLED
        self.result = UseResult.CANCELLED
        self.events.append(
            UseEvent(
                occurred_at=occurred_at,
                type=UseEventType.CANCELLED,
                triggered_by=triggered_by,
                note=reason,
            )
        )

    def record_cancelled_from_proposal(
        self,
        occurred_at: datetime,
        triggered_by: PermissionId,
        reason: str,
    ) -> None:
        self.status = UseStatus.CANCELLED
        self.result = UseResult.CANCELLED
        self.events.append(
            UseEvent(
                occurred_at=occurred_at,
                type=UseEventType.CANCELLED,
                triggered_by=triggered_by,
                note=reason,
            )
        )


@dataclass(frozen=True, slots=True)
class ProposalEvent:
    occurred_at: datetime
    type: ProposalEventType
    triggered_by: PermissionId | None
    note: str | None = None


@dataclass(slots=True)
class RequestedDocument:
    id: RequestedDocumentId
    type: DocumentType
    description: str
    requested_at: datetime
    requested_by: PermissionId


@dataclass(slots=True)
class RequestedObject:
    """Entity carrying the collection-object snapshot requested on a proposal.

    The inventory snapshot lives directly on this entity (Proposal Phase). When
    the proposal is approved, it is copied into a project-owned
    :class:`CollectionUseObject`, which is what journal entries reference."""

    id: RequestedObjectId
    inventory_number: str
    category: str
    description: str
    requested_at: datetime
    requested_by: PermissionId
    display_title: str | None = None
    object_name: str | None = None
    brief_description_snapshot: str | None = None

    def __post_init__(self) -> None:
        if not self.inventory_number:
            raise ValueError("inventoryNumber is required.")


@dataclass(frozen=True, slots=True)
class RequesterContact:
    name: str
    email: EmailAddress


@dataclass(slots=True)
class Document:
    id: DocumentId
    type: DocumentType
    file_name: str
    file_reference: str
    submitted_at: datetime
    submitted_by: PermissionId | None


@dataclass(slots=True)
class Proposal:
    id: ProposalId
    reference_number: ReferenceNumber
    # title/intended_use/dates are optional: a proposal may be created as a stub
    # and completed in a later step.
    title: str | None
    collection_use_project_id: CollectionUseProjectId | None
    intended_use: IntendedUse | None
    begin_date: date | None
    end_date: date | None
    status: ProposalStatus
    requested_by: PermissionId | None
    submitted_at: datetime
    requester_contact: RequesterContact | None = None
    assigned_to: PermissionId | None = None
    events: list[ProposalEvent] = field(default_factory=list)
    requested_documents: list[RequestedDocument] = field(default_factory=list)
    requested_objects: list[RequestedObject] = field(default_factory=list)
    documents: list[Document] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.requested_by is None and self.requester_contact is None:
            raise ValueError(
                "Proposal must have either requested_by or requester_contact"
            )

    def record_submitted(
        self,
        occurred_at: datetime,
        triggered_by: PermissionId | None,
        note: str | None = None,
    ) -> None:
        self.status = ProposalStatus.SUBMITTED
        self.events.append(
            ProposalEvent(
                occurred_at=occurred_at,
                type=ProposalEventType.SUBMITTED,
                triggered_by=triggered_by,
                note=note,
            )
        )

    def edit_details(
        self,
        *,
        title: str | None,
        update_title: bool,
        intended_use: IntendedUse | None,
        update_intended_use: bool,
        begin_date: date | None,
        update_begin_date: bool,
        end_date: date | None,
        update_end_date: bool,
    ) -> None:
        """Staff correction of the proposal's defining metadata.

        Each ``update_*`` flag distinguishes a JSON ``null`` (clear the field)
        from an omitted key (leave unchanged); ``intended_use`` is replaced
        whole when present. Records no event — this is a metadata correction,
        not a lifecycle transition.
        """
        if self.status in _PROPOSAL_TERMINAL_STATUSES:
            raise InvalidTransition(
                "Cannot edit a proposal that is already decided or cancelled"
            )
        if update_title:
            self.title = title
        if update_intended_use:
            self.intended_use = intended_use
        if update_begin_date:
            self.begin_date = begin_date
        if update_end_date:
            self.end_date = end_date
        if (
            self.begin_date is not None
            and self.end_date is not None
            and self.end_date < self.begin_date
        ):
            raise ValueError("endDate must be after beginDate")

    def assign(
        self,
        occurred_at: datetime,
        triggered_by: PermissionId,
        target_permission_id: PermissionId,
        note: str | None = None,
    ) -> None:
        if self.status in _PROPOSAL_TERMINAL_STATUSES:
            raise InvalidTransition(
                "Cannot assign a proposal that is already decided or cancelled"
            )
        self.assigned_to = target_permission_id
        self.status = ProposalStatus.PENDING
        self.events.append(
            ProposalEvent(
                occurred_at=occurred_at,
                type=ProposalEventType.ASSIGNED,
                triggered_by=triggered_by,
                note=note,
            )
        )

    def request_documents(
        self,
        occurred_at: datetime,
        triggered_by: PermissionId,
        docs: list[RequestedDocument],
        note: str | None = None,
    ) -> None:
        if self.status != ProposalStatus.PENDING:
            raise InvalidTransition(
                "Documents can only be requested when proposal is in PENDING status"
            )
        self.requested_documents.extend(docs)
        self.events.append(
            ProposalEvent(
                occurred_at=occurred_at,
                type=ProposalEventType.DOCUMENTS_REQUESTED,
                triggered_by=triggered_by,
                note=note,
            )
        )

    def add_requested_objects(self, objects: list[RequestedObject]) -> None:
        if self.status in _PROPOSAL_TERMINAL_STATUSES:
            raise InvalidTransition(
                "Cannot add requested objects to a decided proposal"
            )
        self.requested_objects.extend(objects)

    def submit_documents(
        self,
        occurred_at: datetime,
        triggered_by: PermissionId,
        document: Document,
    ) -> None:
        if self.status != ProposalStatus.PENDING:
            raise InvalidTransition("Proposal is not in PENDING status")
        self.documents.append(document)
        self.events.append(
            ProposalEvent(
                occurred_at=occurred_at,
                type=ProposalEventType.DOCUMENTS_SUBMITTED,
                triggered_by=triggered_by,
            )
        )

    def forward(
        self,
        occurred_at: datetime,
        triggered_by: PermissionId,
        target_permission_id: PermissionId,
        note: str | None = None,
    ) -> None:
        if self.status != ProposalStatus.PENDING:
            raise InvalidTransition(
                "Proposal must be PENDING to be forwarded to another staff member"
            )
        self.assigned_to = target_permission_id
        self.events.append(
            ProposalEvent(
                occurred_at=occurred_at,
                type=ProposalEventType.FORWARDED,
                triggered_by=triggered_by,
                note=note,
            )
        )

    def approve(
        self,
        occurred_at: datetime,
        triggered_by: PermissionId,
        note: str | None = None,
    ) -> None:
        if self.status != ProposalStatus.PENDING:
            raise InvalidTransition("Proposal must be PENDING to be approved")
        self.status = ProposalStatus.APPROVED
        self.events.append(
            ProposalEvent(
                occurred_at=occurred_at,
                type=ProposalEventType.APPROVED,
                triggered_by=triggered_by,
                note=note,
            )
        )

    def reject(
        self,
        occurred_at: datetime,
        triggered_by: PermissionId,
        reason: str,
    ) -> None:
        if self.status != ProposalStatus.PENDING:
            raise InvalidTransition("Proposal must be PENDING to be rejected")
        self.status = ProposalStatus.REJECTED
        self.events.append(
            ProposalEvent(
                occurred_at=occurred_at,
                type=ProposalEventType.REJECTED,
                triggered_by=triggered_by,
                note=reason,
            )
        )

    def cancel(
        self,
        occurred_at: datetime,
        triggered_by: PermissionId,
        reason: str,
    ) -> None:
        if self.status == ProposalStatus.CANCELLED:
            raise InvalidTransition("Proposal is already CANCELLED")
        if self.status == ProposalStatus.REJECTED:
            raise InvalidTransition("Cannot cancel a rejected proposal")
        self.status = ProposalStatus.CANCELLED
        self.events.append(
            ProposalEvent(
                occurred_at=occurred_at,
                type=ProposalEventType.CANCELLED,
                triggered_by=triggered_by,
                note=reason,
            )
        )


@dataclass(slots=True)
class Message:
    id: MessageId
    sent_at: datetime
    sender: EmailAddress
    recipient: EmailAddress
    subject: str
    body: str
    attachments: list[MessageAttachment] = field(default_factory=list)


@dataclass(slots=True)
class Conversation:
    id: ConversationId
    proposal_id: ProposalId
    messages: list[Message] = field(default_factory=list)
    external_message_id: str | None = None

    @classmethod
    def start(
        cls,
        id: ConversationId,
        proposal_id: ProposalId,
        initial_message: Message,
        external_message_id: str | None = None,
    ) -> Conversation:
        """Business Rule 01: a conversation must start with an email message."""
        return cls(
            id=id,
            proposal_id=proposal_id,
            messages=[initial_message],
            external_message_id=external_message_id,
        )

    def add_message(
        self,
        message: Message,
        proposal_status: ProposalStatus,
    ) -> None:
        if proposal_status in _PROPOSAL_TERMINAL_STATUSES:
            raise InvalidTransition(
                "No messages can be added to a closed or decided proposal"
            )
        self.messages.append(message)
