"""Domain model for the Museum Questions context.

A ``MuseumQuestion`` is a citizen's simple question submitted through the
public "Pergunte ao Museu" channel — a lightweight sibling of the formal
proposal submission flow (``public_submission``), for enquiries that don't
warrant a full in-situ visit request.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class MuseumQuestionStatus(StrEnum):
    SUBMITTED = "SUBMITTED"
    ANSWERED = "ANSWERED"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    CLOSED = "CLOSED"


class MuseumQuestionNotFound(Exception):
    """Raised when a museum question id does not resolve."""


class InvalidMuseumQuestionTransition(Exception):
    """Raised when an action is not valid for the question's current status."""


@dataclass(slots=True)
class MuseumQuestionAttachment:
    id: str
    question_id: str
    file_name: str
    file_reference: str
    content_type: str
    size_bytes: int
    created_at: datetime
    sort_order: int


@dataclass(slots=True)
class MuseumQuestion:
    """Aggregate root — a citizen's question, independent of any proposal or
    account. Created object-free from the public form; the citizen's own
    name/e-mail are captured directly (there is no account, no thread)."""

    id: str
    requester_name: str
    requester_email: str
    subject: str
    message: str
    created_at: datetime
    response_due_at: datetime
    status: MuseumQuestionStatus = MuseumQuestionStatus.SUBMITTED
    answered_at: datetime | None = None
    answered_by: str | None = None
    answer_body: str | None = None
    answer_sent_at: datetime | None = None
    out_of_scope_at: datetime | None = None
    out_of_scope_by: str | None = None
    out_of_scope_reason: str | None = None
    out_of_scope_email_sent_at: datetime | None = None
    closed_at: datetime | None = None
    closed_by: str | None = None
    assigned_to: str | None = None
    response_overdue_notified_at: datetime | None = None
    attachments: list[MuseumQuestionAttachment] | None = None

    def __post_init__(self) -> None:
        if self.attachments is None:
            self.attachments = []

    def answer(
        self,
        *,
        body: str,
        answered_by: str,
        answered_at: datetime,
        sent_at: datetime,
    ) -> None:
        if self.status != MuseumQuestionStatus.SUBMITTED:
            raise InvalidMuseumQuestionTransition(
                "Only submitted questions can be answered."
            )
        body = body.strip()
        if not body:
            raise ValueError("Answer body is required.")
        self.status = MuseumQuestionStatus.ANSWERED
        self.answer_body = body
        self.answered_by = answered_by
        self.answered_at = answered_at
        self.answer_sent_at = sent_at

    def mark_out_of_scope(
        self,
        *,
        reason: str | None,
        by: str,
        occurred_at: datetime,
        email_sent_at: datetime,
    ) -> None:
        if self.status != MuseumQuestionStatus.SUBMITTED:
            raise InvalidMuseumQuestionTransition(
                "Only submitted questions can be marked out of scope."
            )
        cleaned_reason = reason.strip() if reason else None
        self.status = MuseumQuestionStatus.OUT_OF_SCOPE
        self.out_of_scope_reason = cleaned_reason or None
        self.out_of_scope_by = by
        self.out_of_scope_at = occurred_at
        self.out_of_scope_email_sent_at = email_sent_at

    def close(self, *, by: str, closed_at: datetime) -> None:
        if self.status not in {
            MuseumQuestionStatus.ANSWERED,
            MuseumQuestionStatus.OUT_OF_SCOPE,
        }:
            raise InvalidMuseumQuestionTransition(
                "Only answered or out-of-scope questions can be closed."
            )
        self.status = MuseumQuestionStatus.CLOSED
        self.closed_by = by
        self.closed_at = closed_at

    def forward(self, *, target_permission_id: str) -> None:
        if self.status != MuseumQuestionStatus.SUBMITTED:
            raise InvalidMuseumQuestionTransition(
                "Only submitted questions can be forwarded."
            )
        self.assigned_to = target_permission_id

    def is_unanswered_overdue(self, now: datetime) -> bool:
        return (
            self.status == MuseumQuestionStatus.SUBMITTED
            and self.answered_at is None
            and self.response_due_at <= now
        )

    def mark_response_overdue_notified(self, notified_at: datetime) -> None:
        self.response_overdue_notified_at = notified_at
