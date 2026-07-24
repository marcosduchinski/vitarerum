"""Proposal-phase use cases (plus the proposal's conversation).

Everything you do *to a proposal*: submit, enrich, route through staff, and the
researcher/staff messaging on its conversation. The Proposal↔Project bridges
(approve, cancel) live in ``project`` — this module never creates or mutates a
``CollectionUseProject``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from app.identity.public import Actor, GroupName
from app.reference_numbers.public import ReferenceKind
from app.shared.authorization import require_group, require_staff
from app.use_of_collections.application.ports import (
    ConversationRepository,
    FileStoragePort,
    ProposalRepository,
    ReferenceNumberGeneratorPort,
)
from app.use_of_collections.application.use_cases._shared import (
    _actor_email,
    _file_reference,
    _new_id,
    _now,
)
from app.use_of_collections.domain.enums import (
    ProposalStatus,
    SubmissionChannel,
    UseType,
)
from app.use_of_collections.domain.models import (
    Conversation,
    ConversationId,
    Document,
    DocumentCorrectionItem,
    DocumentCorrectionItemId,
    DocumentId,
    DocumentType,
    EmailAddress,
    Message,
    MessageAttachment,
    MessageId,
    PermissionId,
    Proposal,
    ProposalId,
    RequestedDocument,
    RequestedDocumentId,
    RequestedObject,
    RequestedObjectId,
    RequesterContact,
)

# ── Submit Proposal ───────────────────────────────────────────────────────────


@dataclass(slots=True)
class SubmitProposalInput:
    # title/intended_use/purpose/dates are optional: a proposal may be created
    # as a stub and completed in a later step.
    title: str | None
    intended_use: UseType | None
    purpose: str | None
    begin_date: date | None
    end_date: date | None
    requested_by: Actor | None
    submission_channel: SubmissionChannel
    requester_contact: RequesterContact | None = None
    initial_message_sender: str | None = None
    initial_message_recipient: str = "collections@museum.pt"
    initial_message_subject: str = ""
    initial_message_body: str = ""
    initial_message_external_id: str | None = None
    documents: list[Document] = field(default_factory=list)


@dataclass(slots=True)
class SubmitProposalOutput:
    proposal: Proposal
    conversation_id: ConversationId


class SubmitProposal:
    # A proposal is always created object-free: the researcher describes the
    # objects in the initial message as prose, then later searches the catalog
    # and attaches the matches via AddRequestedObjects. There is therefore no
    # object catalog involved at submit time.
    def __init__(
        self,
        proposal_repository: ProposalRepository,
        conversation_repository: ConversationRepository,
        reference_generator: ReferenceNumberGeneratorPort | None = None,
    ) -> None:
        self._proposal_repo = proposal_repository
        self._conversation_repo = conversation_repository
        self._reference_generator = reference_generator

    async def execute(self, data: SubmitProposalInput) -> SubmitProposalOutput:
        if data.requested_by is None and data.requester_contact is None:
            raise ValueError("requester_contact is required without requested_by")
        if (
            data.submission_channel == SubmissionChannel.PUBLIC
            and data.requested_by is not None
        ):
            raise ValueError("Public proposal creation cannot include requested_by")
        now = _now()
        proposal_id = ProposalId(_new_id())
        conversation_id = ConversationId(_new_id())
        reference_number = (
            await self._reference_generator.generate(
                kind=ReferenceKind.PROPOSAL, on_date=now.date()
            )
            if self._reference_generator is not None
            else await self._proposal_repo.next_reference_number_for(now.date())
        )

        proposal = Proposal(
            id=proposal_id,
            reference_number=reference_number,
            title=(
                data.title if data.title is not None else data.initial_message_subject
            ),
            collection_use_project_id=None,
            intended_use=data.intended_use,
            begin_date=data.begin_date,
            end_date=data.end_date,
            status=ProposalStatus.SUBMITTED,
            requested_by=(
                data.requested_by.id if data.requested_by is not None else None
            ),
            submitted_at=now,
            submission_channel=data.submission_channel,
            requester_contact=data.requester_contact,
        )
        proposal.documents = list(data.documents)
        proposal.record_submitted(
            occurred_at=now,
            triggered_by=(
                data.requested_by.id if data.requested_by is not None else None
            ),
        )

        if data.initial_message_sender is not None:
            sender_email = data.initial_message_sender
        elif data.requested_by is not None:
            sender_email = _actor_email(data.requested_by)
        else:
            assert data.requester_contact is not None
            sender_email = data.requester_contact.email.value
        initial_message = Message(
            id=MessageId(_new_id()),
            sent_at=now,
            sender=EmailAddress(sender_email),
            recipient=EmailAddress(data.initial_message_recipient),
            subject=data.initial_message_subject or data.title or "",
            body=data.initial_message_body or data.purpose or "",
        )
        conversation = Conversation.start(
            id=conversation_id,
            proposal_id=proposal_id,
            initial_message=initial_message,
            external_message_id=data.initial_message_external_id,
        )

        await self._proposal_repo.add(proposal)
        await self._conversation_repo.add(conversation)

        return SubmitProposalOutput(
            proposal=proposal,
            conversation_id=conversation_id,
        )


# ── Add Requested Objects ──────────────────────────────────────────────────────


@dataclass(slots=True)
class RequestedObjectSnapshotInput:
    """A requested object whose inventory snapshot is supplied by the caller —
    the user selects objects from a catalog search result, so the display fields
    are already known client-side and arrive with the request.
    ``inventory_number``/``display_title``/``object_name`` are mandatory at the
    API boundary; ``brief_description_snapshot`` is optional."""

    inventory_number: str
    display_title: str
    object_name: str
    brief_description_snapshot: str | None = None
    category: str = ""
    description: str = ""


@dataclass(slots=True)
class AddRequestedObjectsInput:
    proposal_id: ProposalId
    caller: Actor
    objects: list[RequestedObjectSnapshotInput]


class AddRequestedObjects:
    def __init__(self, proposal_repository: ProposalRepository) -> None:
        self._repo = proposal_repository

    async def execute(self, data: AddRequestedObjectsInput) -> Proposal:
        proposal = await self._repo.get_by_id(data.proposal_id)
        if proposal is None:
            raise LookupError(f"No proposal found with id {data.proposal_id}")
        now = _now()
        resolved = [
            RequestedObject(
                id=RequestedObjectId(_new_id()),
                inventory_number=item.inventory_number,
                display_title=item.display_title,
                object_name=item.object_name,
                brief_description_snapshot=item.brief_description_snapshot,
                category=item.category,
                description=item.description,
                requested_at=now,
            )
            for item in data.objects
        ]
        proposal.add_requested_objects(resolved)
        await self._repo.save(proposal)
        return proposal


@dataclass(slots=True)
class RemoveRequestedObjectInput:
    proposal_id: ProposalId
    requested_object_id: RequestedObjectId
    caller: Actor


class RemoveRequestedObject:
    def __init__(self, proposal_repository: ProposalRepository) -> None:
        self._repo = proposal_repository

    async def execute(self, data: RemoveRequestedObjectInput) -> Proposal:
        proposal = await self._repo.get_by_id(data.proposal_id)
        if proposal is None:
            raise LookupError(f"No proposal found with id {data.proposal_id}")
        proposal.remove_requested_object(data.requested_object_id)
        await self._repo.save(proposal)
        return proposal


# ── Edit Proposal Details ─────────────────────────────────────────────────────


@dataclass(slots=True)
class EditProposalDetailsInput:
    proposal_id: ProposalId
    caller: Actor
    title: str | None = None
    update_title: bool = False
    intended_use: UseType | None = None
    update_intended_use: bool = False
    begin_date: date | None = None
    update_begin_date: bool = False
    end_date: date | None = None
    update_end_date: bool = False


class EditProposalDetails:
    def __init__(self, proposal_repository: ProposalRepository) -> None:
        self._repo = proposal_repository

    async def execute(self, data: EditProposalDetailsInput) -> Proposal:
        proposal = await self._repo.get_by_id(data.proposal_id)
        if proposal is None:
            raise LookupError(f"No proposal found with id {data.proposal_id}")
        proposal.edit_details(
            title=data.title,
            update_title=data.update_title,
            intended_use=data.intended_use,
            update_intended_use=data.update_intended_use,
            begin_date=data.begin_date,
            update_begin_date=data.update_begin_date,
            end_date=data.end_date,
            update_end_date=data.update_end_date,
        )
        await self._repo.save(proposal)
        return proposal


# ── Assign Proposal ───────────────────────────────────────────────────────────


@dataclass(slots=True)
class AssignProposalInput:
    proposal_id: ProposalId
    caller: Actor
    target_permission_id: PermissionId | None = None
    note: str | None = None


class AssignProposal:
    def __init__(self, proposal_repository: ProposalRepository) -> None:
        self._repo = proposal_repository

    async def execute(self, data: AssignProposalInput) -> Proposal:
        proposal = await self._repo.get_by_id(data.proposal_id)
        if proposal is None:
            raise LookupError(f"No proposal found with id {data.proposal_id}")
        target = data.target_permission_id or data.caller.id
        proposal.assign(
            occurred_at=_now(),
            triggered_by=data.caller.id,
            target_permission_id=target,
            note=data.note,
        )
        await self._repo.save(proposal)
        return proposal


# ── Request Documents ─────────────────────────────────────────────────────────


@dataclass(slots=True)
class RequestedDocumentInput:
    doc_type: str
    description: str


@dataclass(slots=True)
class RequestDocumentsInput:
    proposal_id: ProposalId
    caller: Actor
    required_documents: list[RequestedDocumentInput]
    note: str | None = None


class RequestDocuments:
    def __init__(self, proposal_repository: ProposalRepository) -> None:
        self._repo = proposal_repository

    async def execute(self, data: RequestDocumentsInput) -> Proposal:
        proposal = await self._repo.get_by_id(data.proposal_id)
        if proposal is None:
            raise LookupError(f"No proposal found with id {data.proposal_id}")
        now = _now()
        docs = [
            RequestedDocument(
                id=RequestedDocumentId(_new_id()),
                type=DocumentType(d.doc_type),
                description=d.description,
                requested_at=now,
                requested_by=data.caller.id,
            )
            for d in data.required_documents
        ]
        proposal.request_documents(
            occurred_at=now,
            triggered_by=data.caller.id,
            docs=docs,
            note=data.note,
        )
        await self._repo.save(proposal)
        return proposal


# ── Submit Documents ──────────────────────────────────────────────────────────


@dataclass(slots=True)
class SubmitDocumentsInput:
    proposal_id: ProposalId
    caller: Actor
    file_content: bytes
    file_name: str
    document_type: str


class SubmitDocuments:
    def __init__(
        self,
        proposal_repository: ProposalRepository,
        file_storage: FileStoragePort,
    ) -> None:
        self._repo = proposal_repository
        self._storage = file_storage

    async def execute(self, data: SubmitDocumentsInput) -> Document:
        proposal = await self._repo.get_by_id(data.proposal_id)
        if proposal is None:
            raise LookupError(f"No proposal found with id {data.proposal_id}")
        now = _now()
        reference = _file_reference("proposals", str(data.proposal_id), data.file_name)
        file_reference = await self._storage.save(data.file_content, reference)
        try:
            document = Document(
                id=DocumentId(_new_id()),
                type=DocumentType(data.document_type),
                file_name=data.file_name,
                file_reference=file_reference,
                submitted_at=now,
                submitted_by=data.caller.id,
            )
            proposal.submit_documents(
                occurred_at=now,
                triggered_by=data.caller.id,
                document=document,
            )
            await self._repo.save(proposal)
        except BaseException:
            # Don't leave an orphaned file when the aggregate fails to persist.
            await self._storage.delete(file_reference)
            raise
        return document


# ── Forward Proposal ──────────────────────────────────────────────────────────


@dataclass(slots=True)
class ForwardProposalInput:
    proposal_id: ProposalId
    caller: Actor
    target_permission_id: PermissionId
    note: str | None = None


class ForwardProposal:
    def __init__(self, proposal_repository: ProposalRepository) -> None:
        self._repo = proposal_repository

    async def execute(self, data: ForwardProposalInput) -> Proposal:
        proposal = await self._repo.get_by_id(data.proposal_id)
        if proposal is None:
            raise LookupError(f"No proposal found with id {data.proposal_id}")
        # Caller-is-staff and target-exists-and-is-staff (422
        # INVALID_PERMISSION_TARGET) are enforced at the route via
        # require_staff / _require_staff_permission_target; the PENDING-status
        # guard lives in Proposal.forward().
        proposal.forward(
            occurred_at=_now(),
            triggered_by=data.caller.id,
            target_permission_id=data.target_permission_id,
            note=data.note,
        )
        await self._repo.save(proposal)
        return proposal


# ── Reject Proposal ───────────────────────────────────────────────────────────


@dataclass(slots=True)
class RejectProposalInput:
    proposal_id: ProposalId
    caller: Actor
    reason: str
    requester_email: str


@dataclass(slots=True)
class RejectProposalOutput:
    proposal: Proposal


class RejectProposal:
    def __init__(
        self,
        proposal_repository: ProposalRepository,
        conversation_repository: ConversationRepository,
    ) -> None:
        self._proposal_repo = proposal_repository
        self._conversation_repo = conversation_repository

    async def execute(self, data: RejectProposalInput) -> RejectProposalOutput:
        require_group(data.caller, GroupName.CURATORIAL)
        proposal = await self._proposal_repo.get_by_id(data.proposal_id)
        if proposal is None:
            raise LookupError(f"No proposal found with id {data.proposal_id}")
        conversation = await self._conversation_repo.get_by_proposal_id(
            data.proposal_id
        )
        if conversation is None:
            raise LookupError("Conversation not found for this proposal")

        now = _now()
        message = Message(
            id=MessageId(_new_id()),
            sent_at=now,
            sender=EmailAddress(_actor_email(data.caller)),
            recipient=EmailAddress(data.requester_email),
            subject=f"Proposal rejected: {proposal.reference_number.value}",
            body=data.reason,
        )
        conversation.add_message(message, proposal.status)
        proposal.reject(
            occurred_at=now, triggered_by=data.caller.id, reason=data.reason
        )
        await self._proposal_repo.save(proposal)
        await self._conversation_repo.save(conversation)
        return RejectProposalOutput(proposal=proposal)


# ── Document Corrections ──────────────────────────────────────────────────────


@dataclass(slots=True)
class DocumentCorrectionInput:
    document_type: str
    reason: str
    # None ⇒ a missing document is requested (document_type is the only scope).
    document_id: str | None = None


@dataclass(slots=True)
class RequestDocumentCorrectionsInput:
    proposal_id: ProposalId
    caller: Actor
    items: list[DocumentCorrectionInput]
    requester_email: str
    requester_name: str
    note: str | None = None


@dataclass(slots=True)
class RequestDocumentCorrectionsOutput:
    proposal: Proposal
    correction_item_ids: list[str]
    requester_email: str
    requester_name: str


class RequestDocumentCorrections:
    """Staff asks the requester to correct/replace or supply documents.

    Instructory action — keeps the proposal PENDING (unlike ``reject``). Records
    the durable :class:`DocumentCorrectionItem`s + event. The tokenised e-mail
    invitation is dispatched by the route AFTER commit via
    :class:`AmendmentInvitationPort`, so the citizen never gets a link whose token
    (or items) failed to persist."""

    def __init__(self, proposal_repository: ProposalRepository) -> None:
        self._repo = proposal_repository

    async def execute(
        self, data: RequestDocumentCorrectionsInput
    ) -> RequestDocumentCorrectionsOutput:
        require_staff(data.caller)
        proposal = await self._repo.get_by_id(data.proposal_id)
        if proposal is None:
            raise LookupError(f"No proposal found with id {data.proposal_id}")
        now = _now()
        items = [
            DocumentCorrectionItem(
                id=DocumentCorrectionItemId(_new_id()),
                document_type=DocumentType(item.document_type),
                reason=item.reason,
                requested_at=now,
                requested_by=data.caller.id,
                document_id=DocumentId(item.document_id)
                if item.document_id is not None
                else None,
            )
            for item in data.items
        ]
        proposal.request_document_corrections(
            occurred_at=now,
            triggered_by=data.caller.id,
            items=items,
            note=data.note,
        )
        await self._repo.save(proposal)
        return RequestDocumentCorrectionsOutput(
            proposal=proposal,
            correction_item_ids=[item.id for item in items],
            requester_email=data.requester_email,
            requester_name=data.requester_name,
        )


class CorrectionScopeError(Exception):
    """An amendment upload/removal fell outside the token's authorised scope."""


@dataclass(slots=True)
class SubmitAmendmentDocumentInput:
    proposal_id: ProposalId
    file_content: bytes
    file_name: str
    document_type: str
    # Document types the amendment token authorises (derived from its still-open
    # correction items). Enforced here so the scope rule lives in the use case,
    # mirroring how RemoveAmendmentDocument delegates ``allowed_ids``.
    allowed_document_types: set[str]


class SubmitAmendmentDocument:
    """Public (unauthenticated) document upload during an amendment.

    Mirrors :class:`SubmitDocuments` but carries no ``Actor`` — the citizen has no
    account, so ``submitted_by`` is ``None``. Enforces the token-derived
    ``allowed_document_types`` scope before persisting."""

    def __init__(
        self,
        proposal_repository: ProposalRepository,
        file_storage: FileStoragePort,
    ) -> None:
        self._repo = proposal_repository
        self._storage = file_storage

    async def execute(self, data: SubmitAmendmentDocumentInput) -> Document:
        # Normalise first (trim/length via the value object) so the scope check
        # compares the same trimmed form that ``allowed_document_types`` holds.
        document_type = DocumentType(data.document_type)
        if document_type.value not in data.allowed_document_types:
            raise CorrectionScopeError(
                f"Document type {document_type.value} is not being requested "
                "for correction."
            )
        proposal = await self._repo.get_by_id(data.proposal_id)
        if proposal is None:
            raise LookupError(f"No proposal found with id {data.proposal_id}")
        now = _now()
        reference = _file_reference("proposals", str(data.proposal_id), data.file_name)
        file_reference = await self._storage.save(data.file_content, reference)
        try:
            document = Document(
                id=DocumentId(_new_id()),
                type=document_type,
                file_name=data.file_name,
                file_reference=file_reference,
                submitted_at=now,
                submitted_by=None,
            )
            proposal.submit_documents(
                occurred_at=now,
                triggered_by=None,
                document=document,
            )
            await self._repo.save(proposal)
        except BaseException:
            await self._storage.delete(file_reference)
            raise
        return document


@dataclass(slots=True)
class RemoveAmendmentDocumentInput:
    proposal_id: ProposalId
    document_id: DocumentId
    allowed_ids: set[DocumentId]


class RemoveAmendmentDocument:
    """Remove a document that is within the amendment token's scope.

    ``allowed_ids`` is the token-authorised set; the aggregate enforces the
    PENDING + scope guards. The stored file is reclaimed after the aggregate is
    persisted."""

    def __init__(
        self,
        proposal_repository: ProposalRepository,
        file_storage: FileStoragePort,
    ) -> None:
        self._repo = proposal_repository
        self._storage = file_storage

    async def execute(self, data: RemoveAmendmentDocumentInput) -> None:
        proposal = await self._repo.get_by_id(data.proposal_id)
        if proposal is None:
            raise LookupError(f"No proposal found with id {data.proposal_id}")
        document = proposal.remove_document(
            data.document_id, allowed_ids=data.allowed_ids
        )
        await self._repo.save(proposal)
        await self._storage.delete(document.file_reference)


@dataclass(slots=True)
class SubmitAmendmentCorrectionsInput:
    proposal_id: ProposalId
    item_ids: list[str] | None = None


class SubmitAmendmentCorrections:
    """Citizen signals the amendment is complete; resolves the correction items."""

    def __init__(self, proposal_repository: ProposalRepository) -> None:
        self._repo = proposal_repository

    async def execute(self, data: SubmitAmendmentCorrectionsInput) -> Proposal:
        proposal = await self._repo.get_by_id(data.proposal_id)
        if proposal is None:
            raise LookupError(f"No proposal found with id {data.proposal_id}")
        item_ids = (
            [DocumentCorrectionItemId(i) for i in data.item_ids]
            if data.item_ids is not None
            else None
        )
        proposal.submit_document_corrections(
            occurred_at=_now(),
            triggered_by=None,
            item_ids=item_ids,
        )
        await self._repo.save(proposal)
        return proposal


# ── Send Message ──────────────────────────────────────────────────────────────


@dataclass(slots=True)
class SendMessageInput:
    proposal_id: ProposalId
    caller: Actor
    recipient: str
    subject: str
    body: str
    document_ids: list[str] = field(default_factory=list)


class SendMessage:
    def __init__(
        self,
        proposal_repository: ProposalRepository,
        conversation_repository: ConversationRepository,
    ) -> None:
        self._proposal_repo = proposal_repository
        self._conversation_repo = conversation_repository

    async def execute(self, data: SendMessageInput) -> Message:
        proposal = await self._proposal_repo.get_by_id(data.proposal_id)
        if proposal is None:
            raise LookupError(f"No proposal found with id {data.proposal_id}")
        conversation = await self._conversation_repo.get_by_proposal_id(
            data.proposal_id
        )
        if conversation is None:
            raise LookupError("Conversation not found for this proposal")

        attachments: list[MessageAttachment] = []
        if data.document_ids:
            documents_by_id = {d.id: d for d in proposal.documents}
            for document_id in data.document_ids:
                document = documents_by_id.get(DocumentId(document_id))
                if document is None:
                    raise LookupError(
                        f"No document {document_id} found on this proposal"
                    )
                attachments.append(
                    MessageAttachment(
                        document_id=document.id,
                        file_name=document.file_name,
                    )
                )

        message = Message(
            id=MessageId(_new_id()),
            sent_at=_now(),
            sender=EmailAddress(_actor_email(data.caller)),
            recipient=EmailAddress(data.recipient),
            subject=data.subject,
            body=data.body,
            attachments=attachments,
        )
        conversation.add_message(message, proposal.status)
        await self._conversation_repo.save(conversation)
        return message
