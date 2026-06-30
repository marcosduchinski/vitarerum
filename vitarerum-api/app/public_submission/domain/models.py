"""Domain model for the public proposal submission context.

A ``PendingPublicSubmission`` is the *pending, unverified* record created by the
double opt-in flow: step 1 stores it, step 2 confirms it (materialising the real
proposal in the staff queue). It owns only its own state — the proposal it
becomes lives in the Use of Collections context and is referenced by its
human-readable reference number once materialised.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum

from app.shared.kernel import UseType


class InvalidTransition(Exception):
    """Raised on an illegal state change of a pending submission."""


class PendingSubmissionStatus(StrEnum):
    PENDING_CONFIRMATION = "PENDING_CONFIRMATION"
    CONFIRMED = "CONFIRMED"


@dataclass(slots=True)
class PendingPublicSubmission:
    """Aggregate root — a citizen's unverified proposal request.

    Created object-free from the public form; the citizen's own name/e-mail are
    captured as the requester contact (there is no account). ``token`` is the
    opaque single-use handle e-mailed to the citizen; confirming it materialises
    the proposal and stamps ``proposal_reference``.
    """

    id: str
    token: str
    citizen_name: str
    citizen_email: str
    subject: str
    body: str
    use_type: UseType
    consent: bool
    created_at: datetime
    # Optional dates the citizen proposes for the use; seed the materialised
    # proposal's begin/end on confirm (the staff may refine them later).
    proposed_begin_date: date | None = None
    proposed_end_date: date | None = None
    status: PendingSubmissionStatus = PendingSubmissionStatus.PENDING_CONFIRMATION
    confirmed_at: datetime | None = None
    proposal_reference: str | None = None

    @property
    def is_confirmed(self) -> bool:
        return self.status is PendingSubmissionStatus.CONFIRMED

    def is_expired(self, now: datetime, ttl: timedelta) -> bool:
        """A pending (unconfirmed) submission expires ``ttl`` after creation.

        A confirmed submission never expires — its link stays idempotent."""
        if self.is_confirmed:
            return False
        return now - self.created_at > ttl

    def confirm(self, proposal_reference: str, occurred_at: datetime) -> None:
        if self.is_confirmed:
            raise InvalidTransition("Pending submission is already confirmed")
        self.status = PendingSubmissionStatus.CONFIRMED
        self.proposal_reference = proposal_reference
        self.confirmed_at = occurred_at
