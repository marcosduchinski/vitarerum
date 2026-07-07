"""Domain model for the Museum Question Triage context.

Given a public "Pergunte ao Museu" question, the pipeline decides whether it
is in scope (collection use, especially an in-situ investigation visit — see
docs/plans/museum-questions-response-section-plan.md, "Regra de escopo") or
out of scope (exhibitions, loans, events, education, other museum services),
and — when in scope and a specific object is named — records what the
catalogue search found for it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import NewType

TriageId = NewType("TriageId", str)


@dataclass(frozen=True, slots=True)
class MentionedObject:
    """One object/specimen name extracted from the question, kept in both
    languages so the catalogue can be searched in either — English and
    Portuguese are both required (a missing translation falls back to the
    other language, never left blank)."""

    english: str
    portuguese: str


class TriageVerdict(StrEnum):
    IN_SCOPE = "IN_SCOPE"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"


@dataclass(frozen=True, slots=True)
class QuestionView:
    """This context's own read-only view of a museum question — decoupled
    from ``app.museum_questions.public.QuestionSummaryView`` by the ACL, so
    this domain never imports another bounded context's types."""

    id: str
    subject: str
    message: str
    requester_email: str
    status: str


@dataclass(frozen=True, slots=True)
class TriageClassification:
    """Structured output of the classification model call."""

    is_visit_related: bool
    mentioned_objects: list[MentionedObject] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ObjectHitView:
    """One catalogue search hit worth showing to staff."""

    collection_id: str
    collection_name: str
    file_name: str
    highlight: str


@dataclass(frozen=True, slots=True)
class ObjectTriageMatch:
    """The catalogue search results for one object name extracted from the
    question — searched in both languages, hits merged and deduplicated. An
    empty ``hits`` list is a valid, displayable outcome ("not found in
    catalogue")."""

    english: str
    portuguese: str
    hits: list[ObjectHitView]


@dataclass(slots=True)
class MessageTriage:
    """A persisted triage run — one immutable row per run. Staff may re-run
    triage on the same question; each run is kept as history."""

    id: TriageId
    question_id: str
    verdict: TriageVerdict
    is_visit_related: bool
    mentioned_objects: list[MentionedObject]
    object_matches: list[ObjectTriageMatch]
    suggested_reply: str | None
    llm_model: str
    created_at: datetime

    @classmethod
    def create(
        cls,
        *,
        question_id: str,
        verdict: TriageVerdict,
        is_visit_related: bool,
        mentioned_objects: list[MentionedObject],
        object_matches: list[ObjectTriageMatch],
        suggested_reply: str | None,
        llm_model: str,
    ) -> MessageTriage:
        """Build a fresh triage run, assigning the id and stamping
        ``created_at``."""
        return cls(
            id=TriageId(str(uuid.uuid4())),
            question_id=question_id,
            verdict=verdict,
            is_visit_related=is_visit_related,
            mentioned_objects=mentioned_objects,
            object_matches=object_matches,
            suggested_reply=suggested_reply,
            llm_model=llm_model,
            created_at=datetime.now(UTC),
        )
