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
    DocumentId as DocumentId,
)
from app.shared.kernel import (
    DocumentType as DocumentType,
)
from app.shared.kernel import (
    EmailAddress as EmailAddress,
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
    DocumentCorrectionStatus,
    MediaType,
    ProposalEventType,
    ProposalStatus,
    SubmissionChannel,
    UseEventType,
    UseResult,
    UseStatus,
    UseType,
)

CollectionUseProjectId = NewType("CollectionUseProjectId", str)
CollectionUseObjectId = NewType("CollectionUseObjectId", str)
ObjectAccessLogId = NewType("ObjectAccessLogId", str)
ObjectLogEntryId = NewType("ObjectLogEntryId", str)
ObjectOccurrenceLogId = NewType("ObjectOccurrenceLogId", str)
ObjectOccurrenceEntryId = NewType("ObjectOccurrenceEntryId", str)
PublicationLogId = NewType("PublicationLogId", str)
PublicationLogEntryId = NewType("PublicationLogEntryId", str)
StaffProjectTodoItemId = NewType("StaffProjectTodoItemId", str)
ProposalId = NewType("ProposalId", str)
RequestedDocumentId = NewType("RequestedDocumentId", str)
DocumentCorrectionItemId = NewType("DocumentCorrectionItemId", str)
RequestedObjectId = NewType("RequestedObjectId", str)
ConversationId = NewType("ConversationId", str)
MessageId = NewType("MessageId", str)

_PROPOSAL_TERMINAL_STATUSES = {
    ProposalStatus.APPROVED,
    ProposalStatus.REJECTED,
    ProposalStatus.CANCELLED,
}
_PROJECT_EDITABLE_STATUSES = {
    UseStatus.CREATED,
    UseStatus.IN_PROGRESS,
}


class InvalidTransition(ValueError):
    pass


class ProjectObjectInUse(Exception):
    pass


class UnsatisfiedCorrection(ValueError):
    """A correction item was submitted without a document that satisfies it."""

    pass


@dataclass(frozen=True, slots=True)
class Attachment:
    file_reference: str
    file_name: str
    media_type: MediaType
    uploaded_at: datetime
    description: str

    def __post_init__(self) -> None:
        if not self.description.strip():
            raise ValueError("description is required.")


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

    def remove_attachment(self, file_reference: str) -> Attachment:
        for index, attachment in enumerate(self.attachments):
            if attachment.file_reference == file_reference:
                return self.attachments.pop(index)
        raise LookupError(f"No attachment found with file reference {file_reference}")

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

    def remove_attachment(self, file_reference: str) -> Attachment:
        for index, attachment in enumerate(self.attachments):
            if attachment.file_reference == file_reference:
                return self.attachments.pop(index)
        raise LookupError(f"No attachment found with file reference {file_reference}")

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
    derived from the project, with optional file attachments.

    ``collection_use_object_id`` is optional: a publication entry may concern a
    specific collection object (a note/citation about that specimen), or none
    at all (a general remark about the project)."""

    id: PublicationLogEntryId
    publication_log_id: PublicationLogId
    added_at: datetime
    added_by: PermissionId
    note: str
    attachments: list[Attachment] = field(default_factory=list)
    collection_use_object_id: CollectionUseObjectId | None = None

    def __post_init__(self) -> None:
        if not self.note:
            raise ValueError("note is required.")

    def add_attachment(self, attachment: Attachment) -> None:
        self.attachments.append(attachment)

    def remove_attachment(self, file_reference: str) -> Attachment:
        for index, attachment in enumerate(self.attachments):
            if attachment.file_reference == file_reference:
                return self.attachments.pop(index)
        raise LookupError(f"No attachment found with file reference {file_reference}")

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
    collection_id: str | None = None
    collection_name: str | None = None

    def __post_init__(self) -> None:
        if not self.inventory_number:
            raise ValueError("inventoryNumber is required.")


@dataclass(slots=True)
class StaffProjectTodoItem:
    id: StaffProjectTodoItemId
    project_id: CollectionUseProjectId
    owner_permission_id: PermissionId
    text: str
    completed: bool
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
    position: int = 0

    def __post_init__(self) -> None:
        self.text = _clean_todo_text(self.text)
        if self.position < 0:
            raise ValueError("position must be greater than or equal to 0")

    def rename(self, text: str, now: datetime) -> None:
        self.text = _clean_todo_text(text)
        self.updated_at = now

    def mark_completed(self, now: datetime) -> None:
        if self.completed:
            return
        self.completed = True
        self.completed_at = now
        self.updated_at = now

    def mark_open(self, now: datetime) -> None:
        if not self.completed:
            return
        self.completed = False
        self.completed_at = None
        self.updated_at = now

    def move_to(self, position: int, now: datetime) -> None:
        if position < 0:
            raise ValueError("position must be greater than or equal to 0")
        self.position = position
        self.updated_at = now


def _clean_todo_text(text: str) -> str:
    cleaned = text.strip()
    if not cleaned:
        raise ValueError("text is required")
    if len(cleaned) > 160:
        raise ValueError("text must be at most 160 characters")
    return cleaned


@dataclass(slots=True)
class CollectionUseProject:
    id: CollectionUseProjectId
    reference_number: ReferenceNumber
    title: str
    purpose: str
    intended_use: UseType
    status: UseStatus
    begin_date: date
    end_date: date
    requested_by: PermissionId
    proposal_id: ProposalId | None = None
    origin_project_id: CollectionUseProjectId | None = None
    request_note: str | None = None
    note: str | None = None
    result: UseResult | None = None
    authorised_by: PermissionId | None = None
    authorised_at: datetime | None = None
    events: list[UseEvent] = field(default_factory=list)
    objects: list[CollectionUseObject] = field(default_factory=list)

    def edit(
        self,
        *,
        title: str | None,
        update_title: bool,
        purpose: str | None,
        update_purpose: bool,
        begin_date: date | None,
        update_begin_date: bool,
        end_date: date | None,
        update_end_date: bool,
    ) -> None:
        """Staff correction of project metadata; not a lifecycle transition."""
        if self.status not in _PROJECT_EDITABLE_STATUSES:
            raise InvalidTransition(
                "Cannot edit a project that is already completed or cancelled"
            )
        if update_title:
            if title is None or not title.strip():
                raise ValueError("title is required")
            self.title = title
        if update_purpose:
            if purpose is None or not purpose.strip():
                raise ValueError("purpose is required")
            self.purpose = purpose
        if update_begin_date:
            if begin_date is None:
                raise ValueError("beginDate is required")
            self.begin_date = begin_date
        if update_end_date:
            if end_date is None:
                raise ValueError("endDate is required")
            self.end_date = end_date
        if self.end_date < self.begin_date:
            raise ValueError("endDate must be after beginDate")

    def add_objects(self, objects: list[CollectionUseObject]) -> None:
        if self.status not in _PROJECT_EDITABLE_STATUSES:
            raise InvalidTransition(
                "Cannot add objects to a project that is already completed or cancelled"
            )
        self.objects.extend(objects)

    def remove_object(self, object_id: CollectionUseObjectId) -> None:
        if self.status not in _PROJECT_EDITABLE_STATUSES:
            raise InvalidTransition(
                "Cannot remove objects from a project that is already completed "
                "or cancelled"
            )
        project_object = next(
            (obj for obj in self.objects if obj.id == object_id), None
        )
        if project_object is None:
            raise LookupError(f"No project object found with id {object_id}")
        self.objects.remove(project_object)

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
        if not self.objects:
            raise InvalidTransition(
                "Project must have at least one object before completion"
            )
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
    display_title: str | None = None
    object_name: str | None = None
    brief_description_snapshot: str | None = None
    requested_by: PermissionId | None = None
    collection_id: str | None = None
    collection_name: str | None = None

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
class DocumentCorrectionItem:
    """Staff-issued request to correct/replace or supply a specific document.

    ``document_id`` points at the offending :class:`Document` when the item is a
    correction/replacement; it is ``None`` when the item asks for a *missing*
    document, in which case ``document_type`` is the only scope. This is the
    durable audit record of what was asked — the amendment token (public
    submission context) merely references these items by id."""

    id: DocumentCorrectionItemId
    document_type: DocumentType
    reason: str
    requested_at: datetime
    requested_by: PermissionId
    document_id: DocumentId | None = None
    status: DocumentCorrectionStatus = DocumentCorrectionStatus.REQUESTED
    resolved_at: datetime | None = None


@dataclass(slots=True)
class Proposal:
    id: ProposalId
    reference_number: ReferenceNumber
    # title/intended_use/dates are optional: a proposal may be created as a stub
    # and completed in a later step.
    title: str | None
    collection_use_project_id: CollectionUseProjectId | None
    intended_use: UseType | None
    begin_date: date | None
    end_date: date | None
    status: ProposalStatus
    requested_by: PermissionId | None
    submitted_at: datetime
    submission_channel: SubmissionChannel
    requester_contact: RequesterContact | None = None
    assigned_to: PermissionId | None = None
    events: list[ProposalEvent] = field(default_factory=list)
    requested_documents: list[RequestedDocument] = field(default_factory=list)
    requested_objects: list[RequestedObject] = field(default_factory=list)
    documents: list[Document] = field(default_factory=list)
    correction_items: list[DocumentCorrectionItem] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.requested_by is None and self.requester_contact is None:
            raise ValueError(
                "Proposal must have either requested_by or requester_contact"
            )
        if (
            self.submission_channel == SubmissionChannel.PUBLIC
            and self.requester_contact is None
        ):
            raise ValueError("Public proposals must have requester_contact")
        if (
            self.submission_channel == SubmissionChannel.AUTHENTICATED
            and self.requested_by is None
        ):
            raise ValueError("Authenticated proposals must have requested_by")

    def resolve_requester(self, permission_id: PermissionId) -> None:
        """Bind a system requester to a proposal submitted via ``requester_contact``.

        Called once, at approval time, once Identity has provisioned (or
        reused) a permission for the public requester's contact — see
        ``ApproveProposal``. Records no event: the requester link is a
        technical prerequisite for the project, not a lifecycle transition
        (the ``APPROVED`` event already audits the decision)."""
        if self.requested_by is not None:
            raise InvalidTransition("Proposal requester is already resolved")
        self.requested_by = permission_id

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
        intended_use: UseType | None,
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

    def remove_requested_object(self, requested_object_id: RequestedObjectId) -> None:
        if self.status in _PROPOSAL_TERMINAL_STATUSES:
            raise InvalidTransition(
                "Cannot remove requested objects from a decided proposal"
            )
        requested_object = next(
            (ro for ro in self.requested_objects if ro.id == requested_object_id),
            None,
        )
        if requested_object is None:
            raise LookupError(
                f"Requested object {requested_object_id} not found on this proposal"
            )
        self.requested_objects.remove(requested_object)

    def submit_documents(
        self,
        occurred_at: datetime,
        triggered_by: PermissionId | None,
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

    def submit_amendment_document(
        self,
        occurred_at: datetime,
        document: Document,
    ) -> list[Document]:
        """Public correction upload: appends ``document`` and atomically detaches
        any document(s) it replaces.

        A document is replaced when it is flagged (``document_id``) by a still
        open (``REQUESTED``) correction item of the same type as the upload —
        the citizen is not required to remove the flagged document by hand
        first. Missing-document items (``document_id is None``) have nothing to
        detach. Returns the detached documents so the caller can reclaim their
        stored files."""
        if self.status != ProposalStatus.PENDING:
            raise InvalidTransition("Proposal is not in PENDING status")
        flagged_ids = {
            item.document_id
            for item in self.correction_items
            if item.status == DocumentCorrectionStatus.REQUESTED
            and item.document_type == document.type
            and item.document_id is not None
        }
        replaced = [d for d in self.documents if d.id in flagged_ids]
        self.documents.append(document)
        for old in replaced:
            self.documents.remove(old)
        self.events.append(
            ProposalEvent(
                occurred_at=occurred_at,
                type=ProposalEventType.DOCUMENTS_SUBMITTED,
                triggered_by=None,
            )
        )
        return replaced

    def request_document_corrections(
        self,
        occurred_at: datetime,
        triggered_by: PermissionId,
        items: list[DocumentCorrectionItem],
        note: str | None = None,
    ) -> None:
        """Staff flags documents needing correction/replacement or supply.

        Keeps the proposal PENDING (this is instructory, not a decision). Each
        item referencing an existing document must match one on this proposal;
        items with ``document_id is None`` request a missing document."""
        if self.status != ProposalStatus.PENDING:
            raise InvalidTransition(
                "Document corrections can only be requested when proposal is "
                "in PENDING status"
            )
        if not items:
            raise ValueError("At least one correction item is required")
        existing_ids = {d.id for d in self.documents}
        for item in items:
            if item.document_id is not None and item.document_id not in existing_ids:
                raise ValueError(
                    f"Document {item.document_id} not found on this proposal"
                )
        self.correction_items.extend(items)
        self.events.append(
            ProposalEvent(
                occurred_at=occurred_at,
                type=ProposalEventType.DOCUMENT_CORRECTIONS_REQUESTED,
                triggered_by=triggered_by,
                note=note,
            )
        )

    def remove_document(
        self,
        document_id: DocumentId,
        *,
        allowed_ids: set[DocumentId],
    ) -> Document:
        """Remove a document that is within the correction scope.

        ``allowed_ids`` is the caller-authorised set (e.g. the amendment token's
        scope). The file itself is deleted by the caller — the aggregate only
        detaches the reference. Returns the removed :class:`Document`."""
        if self.status != ProposalStatus.PENDING:
            raise InvalidTransition(
                "Documents can only be removed when proposal is in PENDING status"
            )
        if document_id not in allowed_ids:
            raise InvalidTransition("Document is not within the correction scope")
        document = next((d for d in self.documents if d.id == document_id), None)
        if document is None:
            raise ValueError(f"Document {document_id} not found on this proposal")
        self.documents.remove(document)
        return document

    def _is_correction_satisfied(self, item: DocumentCorrectionItem) -> bool:
        """A correction is satisfied when a document of its type is present that
        is not the flagged one: for a *missing* document (``document_id is None``)
        any document of that type; for a *replacement* a document of that type
        other than the one flagged (so a fresh upload is required)."""
        return any(
            document.type == item.document_type and document.id != item.document_id
            for document in self.documents
        )

    def submit_document_corrections(
        self,
        occurred_at: datetime,
        triggered_by: PermissionId | None,
        item_ids: list[DocumentCorrectionItemId] | None = None,
    ) -> None:
        """Citizen (or staff) marks correction work done; resolves the items.

        ``item_ids`` narrows which items are resolved; ``None`` resolves every
        still-``REQUESTED`` item. Every item being resolved must be *satisfied*
        by a present document (see :meth:`_is_correction_satisfied`) — otherwise
        the whole submission is rejected and nothing is resolved. Records
        ``DOCUMENT_CORRECTIONS_SUBMITTED``."""
        if self.status != ProposalStatus.PENDING:
            raise InvalidTransition(
                "Corrections can only be submitted when proposal is in PENDING status"
            )
        target = set(item_ids) if item_ids is not None else None
        to_resolve = [
            item
            for item in self.correction_items
            if item.status == DocumentCorrectionStatus.REQUESTED
            and (target is None or item.id in target)
        ]
        unsatisfied = [
            item for item in to_resolve if not self._is_correction_satisfied(item)
        ]
        if unsatisfied:
            types = ", ".join(
                sorted({item.document_type.value for item in unsatisfied})
            )
            raise UnsatisfiedCorrection(f"Missing a corrected document for: {types}")
        for item in to_resolve:
            item.status = DocumentCorrectionStatus.RESOLVED
            item.resolved_at = occurred_at
        self.events.append(
            ProposalEvent(
                occurred_at=occurred_at,
                type=ProposalEventType.DOCUMENT_CORRECTIONS_SUBMITTED,
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

    def ensure_approvable(self) -> None:
        """Non-mutating guard: raise unless this proposal can be approved now.

        Exposed so ``ApproveProposal`` can check eligibility *before* it
        provisions an Identity requester for a public proposal's contact —
        a proposal that isn't PENDING will fail here regardless, so there is
        no reason to touch Identity first. ``approve`` reuses this so the
        rule has one source of truth."""
        if self.status != ProposalStatus.PENDING:
            raise InvalidTransition("Proposal must be PENDING to be approved")

    def approve(
        self,
        occurred_at: datetime,
        triggered_by: PermissionId,
        note: str | None = None,
    ) -> None:
        self.ensure_approvable()
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
