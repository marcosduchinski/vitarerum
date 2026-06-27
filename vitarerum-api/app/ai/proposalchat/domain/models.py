"""ProposalChat domain — pure value objects for AI-assisted intended-use triage.

Framework-free and aggregate-free. The taxonomy (``UseType`` / ``IntendedUse``)
comes from the Shared Kernel; nothing here imports User Request. Suggestions are
ephemeral value objects — there is no aggregate and no repository.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.shared.kernel import IntendedUse, UseType


class EmptyMessageBody(ValueError):
    """The focus message has no analysable content — triage needs text."""


@dataclass(frozen=True, slots=True)
class FocusMessage:
    """The single message being triaged, resolved through its conversation."""

    message_id: str
    subject: str
    body: str
    sender: str
    sent_at: datetime


@dataclass(frozen=True, slots=True)
class ProposalSummary:
    """Read-only summary of the proposal the focus message belongs to.

    ``status`` is a plain string (the User Request status value) so the domain
    stays independent of that context; ``intended_use`` is the value currently on
    the proposal, exposed so the UI can diff *current vs suggested*.
    """

    proposal_id: str
    reference_number: str
    title: str
    status: str
    intended_use: IntendedUse


@dataclass(frozen=True, slots=True)
class ConversationContext:
    """Everything triage needs: the focus message plus the proposal summary.

    A single ACL load produces this; both the context read and the suggestion
    use it.
    """

    conversation_id: str
    focus: FocusMessage
    proposal: ProposalSummary


@dataclass(frozen=True, slots=True)
class Confidence:
    """Model confidence in ``[0.0, 1.0]``."""

    value: float

    def __post_init__(self) -> None:
        if not 0.0 <= self.value <= 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")


@dataclass(frozen=True, slots=True)
class IntendedUseSuggestion:
    """An ephemeral, advisory triage result. Never persisted, never written back
    to the proposal. ``source_*`` echo the analysed ids — the only provenance the
    caller receives."""

    use_type: UseType
    description: str
    confidence: Confidence
    rationale: str
    source_conversation_id: str
    source_message_id: str

    def to_intended_use(self) -> IntendedUse:
        """The suggestion as a Shared Kernel ``IntendedUse`` — applies onto a
        proposal without mapping (same taxonomy)."""
        return IntendedUse(use_type=self.use_type, description=self.description)
