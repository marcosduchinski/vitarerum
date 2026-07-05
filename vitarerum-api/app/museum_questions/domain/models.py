"""Domain model for the Museum Questions context.

A ``MuseumQuestion`` is a citizen's simple question submitted through the
public "Pergunte ao Museu" channel — a lightweight sibling of the formal
proposal submission flow (``public_submission``), for enquiries that don't
warrant a full in-situ visit request. This plan (the public intake page)
only ever produces ``SUBMITTED`` rows; the ``ANSWERED``/``OUT_OF_SCOPE``/
``CLOSED`` transitions and their behaviour belong to the internal response
section (see ``docs/plans/museum-questions-response-section-plan.md``) and
are intentionally not implemented yet — the fields exist now so the schema
does not need to change when that plan lands.
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
