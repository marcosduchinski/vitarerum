"""Published read models for the User Request triage context (Open Host Service).

These are plain application DTOs (no ORM, no Pydantic) handed to downstream
contexts — currently ProposalChat — so they never receive User Request
aggregates directly (Anti-Corruption Layer rule). Re-exported, together with the
composition factory, from ``app.use_of_collections.public``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Protocol

from app.shared.kernel import IntendedUse
from app.use_of_collections.domain.enums import ProposalStatus


@dataclass(frozen=True, slots=True)
class FocusMessageView:
    """One message of a conversation, resolved through the conversation root."""

    message_id: str
    sent_at: datetime
    sender: str
    subject: str
    body: str


@dataclass(frozen=True, slots=True)
class ProposalContextView:
    """The triage context for a focus message: the message plus a summary of the
    proposal its conversation belongs to."""

    conversation_id: str
    focus_message: FocusMessageView
    proposal_id: str
    reference_number: str
    title: str
    status: ProposalStatus
    intended_use: IntendedUse


# ── Project export read-view (consumed by the CIDOC-CRM mapping context) ───────


@dataclass(frozen=True, slots=True)
class ExportAttachmentView:
    """One file attachment hanging off a journal entry."""

    source_id: str
    description: str
    reference: str
    position: int


@dataclass(frozen=True, slots=True)
class ExportObjectView:
    """A requested object on the proposal (carries no attachments)."""

    source_id: str
    description: str
    position: int


@dataclass(frozen=True, slots=True)
class ExportEntryView:
    """A journal entry (occurrence / access log / publication) with attachments."""

    source_id: str
    description: str
    position: int
    attachments: list[ExportAttachmentView] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ProjectExportView:
    """A read-only projection of a CollectionUseProject and its journals, handed
    to the CIDOC-CRM mapping context to build an in-situ visit snapshot."""

    project_id: str
    reference_number: str
    begin_date: date
    end_date: date
    intended_use: IntendedUse
    visitor_name: str
    requested_objects: list[ExportObjectView] = field(default_factory=list)
    in_situ_occurrences: list[ExportEntryView] = field(default_factory=list)
    in_situ_logs: list[ExportEntryView] = field(default_factory=list)
    in_situ_publications: list[ExportEntryView] = field(default_factory=list)


class ProjectExportReader(Protocol):
    """Published read port (OHS): assembles a project + its journals into a
    translated, read-only export view. Returns ``None`` when the project does
    not exist."""

    async def load(self, project_id: str) -> ProjectExportView | None: ...


class ConversationNotFound(Exception):
    """Raised when no conversation exists for the given id."""


class MessageNotFound(Exception):
    """Raised when the conversation has no message with the given id."""


class ProposalContextReader(Protocol):
    """Published read port (OHS): resolves a conversation + focus message into a
    translated, read-only triage context. Raises :class:`ConversationNotFound`
    or :class:`MessageNotFound` rather than returning ``None``."""

    async def load(
        self, conversation_id: str, message_id: str
    ) -> ProposalContextView: ...
