from dataclasses import dataclass, field
from datetime import date
from typing import Protocol

from app.identity.public import Actor
from app.reference_numbers.public import ReferenceKind
from app.use_of_collections.domain.enums import ProposalStatus, UseStatus, UseType
from app.use_of_collections.domain.models import (
    CollectionUseObjectId,
    CollectionUseProject,
    CollectionUseProjectId,
    Conversation,
    ConversationId,
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
    PublicationLog,
    PublicationLogEntry,
    PublicationLogEntryId,
    PublicationLogId,
    ReferenceNumber,
)


@dataclass(slots=True)
class ProjectFilters:
    status: UseStatus | None = None
    use_type: UseType | None = None
    requested_by: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    search: str | None = None


@dataclass(slots=True)
class ProposalFilters:
    statuses: tuple[ProposalStatus, ...] = ()
    use_type: UseType | None = None
    assigned_to: str | None = None
    requested_by: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    search: str | None = None


class CollectionUseProjectRepository(Protocol):
    async def add(self, project: CollectionUseProject) -> None: ...

    async def get_by_id(
        self, project_id: CollectionUseProjectId
    ) -> CollectionUseProject | None: ...

    async def get_by_reference(
        self, reference_number: ReferenceNumber
    ) -> CollectionUseProject | None: ...

    async def save(self, project: CollectionUseProject) -> None: ...

    async def list(
        self,
        filters: ProjectFilters,
        page: int,
        size: int,
    ) -> tuple[list[CollectionUseProject], int]: ...


class ProposalRepository(Protocol):
    async def add(self, proposal: Proposal) -> None: ...

    async def next_reference_number_for(self, day: date) -> ReferenceNumber: ...

    async def get_by_id(self, proposal_id: ProposalId) -> Proposal | None: ...

    async def get_by_project_id(
        self, project_id: CollectionUseProjectId
    ) -> Proposal | None: ...

    async def list_by_project_ids(
        self, project_ids: list[CollectionUseProjectId]
    ) -> list[Proposal]: ...

    async def save(self, proposal: Proposal) -> None: ...

    async def list(
        self,
        filters: ProposalFilters,
        page: int,
        size: int,
    ) -> tuple[list[Proposal], int]: ...


class ConversationRepository(Protocol):
    async def add(self, conversation: Conversation) -> None: ...

    async def get_by_id(
        self, conversation_id: ConversationId
    ) -> Conversation | None: ...

    async def get_by_proposal_id(
        self, proposal_id: ProposalId
    ) -> Conversation | None: ...

    async def get_by_external_message_id(
        self, message_id: str
    ) -> Conversation | None: ...

    async def save(self, conversation: Conversation) -> None: ...


class ObjectAccessLogRepository(Protocol):
    async def add(self, access_log: ObjectAccessLog) -> None: ...

    async def get_by_id(
        self, access_log_id: ObjectAccessLogId
    ) -> ObjectAccessLog | None: ...

    async def get_by_project_id(
        self, project_id: CollectionUseProjectId
    ) -> ObjectAccessLog | None: ...

    async def get_entry_by_id(
        self, entry_id: ObjectLogEntryId
    ) -> ObjectLogEntry | None: ...

    async def save(self, access_log: ObjectAccessLog) -> None: ...

    async def save_entry(self, entry: ObjectLogEntry) -> None: ...

    async def list_entries_for_object(
        self,
        project_id: CollectionUseProjectId,
        collection_use_object_id: CollectionUseObjectId,
    ) -> list[ObjectLogEntry]: ...

    async def remove_entries(self, entry_ids: list[ObjectLogEntryId]) -> None: ...

    async def list_entries_by_project(
        self,
        project_id: CollectionUseProjectId,
        added_by: str | None,
        page: int,
        size: int,
    ) -> tuple[list[ObjectLogEntry], int]: ...

    async def has_entries_for_object(
        self,
        project_id: CollectionUseProjectId,
        collection_use_object_id: CollectionUseObjectId,
    ) -> bool: ...


class ObjectOccurrenceLogRepository(Protocol):
    async def add(self, occurrence_log: ObjectOccurrenceLog) -> None: ...

    async def get_by_id(
        self, occurrence_log_id: ObjectOccurrenceLogId
    ) -> ObjectOccurrenceLog | None: ...

    async def get_by_project_id(
        self, project_id: CollectionUseProjectId
    ) -> ObjectOccurrenceLog | None: ...

    async def get_entry_by_id(
        self, entry_id: ObjectOccurrenceEntryId
    ) -> ObjectOccurrenceEntry | None: ...

    async def save(self, occurrence_log: ObjectOccurrenceLog) -> None: ...

    async def save_entry(self, entry: ObjectOccurrenceEntry) -> None: ...

    async def list_entries_for_object(
        self,
        project_id: CollectionUseProjectId,
        collection_use_object_id: CollectionUseObjectId,
    ) -> list[ObjectOccurrenceEntry]: ...

    async def remove_entries(
        self, entry_ids: list[ObjectOccurrenceEntryId]
    ) -> None: ...

    async def list_entries_by_project(
        self,
        project_id: CollectionUseProjectId,
        reported_by: str | None,
        page: int,
        size: int,
    ) -> tuple[list[ObjectOccurrenceEntry], int]: ...

    async def has_entries_for_object(
        self,
        project_id: CollectionUseProjectId,
        collection_use_object_id: CollectionUseObjectId,
    ) -> bool: ...


class PublicationLogRepository(Protocol):
    async def add(self, publication_log: PublicationLog) -> None: ...

    async def get_by_id(
        self, publication_log_id: PublicationLogId
    ) -> PublicationLog | None: ...

    async def get_by_project_id(
        self, project_id: CollectionUseProjectId
    ) -> PublicationLog | None: ...

    async def get_entry_by_id(
        self, entry_id: PublicationLogEntryId
    ) -> PublicationLogEntry | None: ...

    async def save(self, publication_log: PublicationLog) -> None: ...

    async def save_entry(self, entry: PublicationLogEntry) -> None: ...

    async def list_entries_for_object(
        self,
        project_id: CollectionUseProjectId,
        collection_use_object_id: CollectionUseObjectId,
    ) -> list[PublicationLogEntry]: ...

    async def remove_entries(self, entry_ids: list[PublicationLogEntryId]) -> None: ...

    async def list_entries_by_project(
        self,
        project_id: CollectionUseProjectId,
        added_by: str | None,
        page: int,
        size: int,
    ) -> tuple[list[PublicationLogEntry], int]: ...


class AmendmentInvitationPort(Protocol):
    """Driven port: invite a proposal's requester to correct documents.

    Implemented by the public-submission context (which owns the tokenised,
    unauthenticated amendment channel and the e-mail infra). Defined here and
    published via ``use_of_collections.public`` so the dependency direction stays
    ``public_submission → use_of_collections``. Scope is carried by
    ``correction_item_ids`` — the concrete document ids/types are derived from the
    referenced :class:`DocumentCorrectionItem`s, not duplicated here."""

    async def invite_document_corrections(
        self,
        *,
        proposal_id: ProposalId,
        requester_email: str,
        requester_name: str,
        correction_item_ids: list[str],
    ) -> None: ...


@dataclass(slots=True)
class ResolvedExternalRequester:
    """Minimal local shape of Identity's provisioning result.

    Deliberately narrower than Identity's own ``ProvisionedRequester``: this
    context only ever needs the resulting ``actor`` and, when a new user was
    created, the ``temporary_password`` to relay by e-mail — ``user_created``
    is Identity-internal bookkeeping this context has no use for."""

    actor: Actor
    temporary_password: str | None = field(default=None, repr=False)


class ExternalRequesterProvisioner(Protocol):
    """Driven port: resolve a system requester for a public proposal's contact.

    Called by ``ApproveProposal`` when a public proposal (``requested_by is
    None``) is approved. Implemented by an adapter over Identity's
    ``ProvisionExternalRequester`` (Open Host Service), so this context never
    imports Identity internals directly — only ``identity.public``."""

    async def provision(self, email: str, name: str) -> ResolvedExternalRequester: ...


class RequesterAccessEmailSender(Protocol):
    """Driven port: notify a newly provisioned external requester of their
    login credentials. Only called when ``ExternalRequesterProvisioner``
    actually created a user (see ``ApproveProposal``); an already-existing
    user's e-mail address never receives a new password."""

    async def send_access_created(
        self,
        to_email: str,
        requester_name: str,
        login_url: str,
        temporary_password: str,
    ) -> None: ...


class ReferenceNumberGeneratorPort(Protocol):
    async def generate(
        self, *, kind: ReferenceKind, on_date: date
    ) -> ReferenceNumber: ...


class FileStoragePort(Protocol):
    async def save(self, content: bytes, filename: str) -> str:
        """Persist file bytes and return a fileReference string."""
        ...

    async def read(self, file_reference: str) -> bytes:
        """Read persisted file bytes by fileReference."""
        ...

    async def delete(self, file_reference: str) -> None:
        """Delete a stored file by fileReference (no error if already gone)."""
        ...
