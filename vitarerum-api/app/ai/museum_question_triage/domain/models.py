"""Domain model for the Museum Question Triage context.

Given a public "Pergunte ao Museu" question, the pipeline decides whether it
is in scope (collection use, especially an in-situ investigation visit — see
docs/plans/museum-questions-response-section-plan.md, "Regra de escopo") or
out of scope (exhibitions, loans, events, education, other museum services),
and — when in scope and a specific object is named — records what the
catalogue search found for it.

Mutability policy (docs/plans/museum-questions-ai-triage-refinements-plan.md):
a triage run is not a fully frozen snapshot. ``verdict``/``is_visit_related``
are fixed at creation — they are the AI's raw classification signal, never
rewritten (contesting the verdict only sets ``staff_override_verdict``
alongside it). ``mentioned_objects``, ``object_matches`` and
``suggested_reply`` are revisable state: they start populated by the AI but
can be updated in place afterwards by staff-triggered actions
(``OverrideTriageVerdict``, ``SyncTriageSearchTerms``) — there are no
parallel ``original_*``/``reviewed_*`` fields, just one current state per
run, with per-entry provenance (``MentionedObjectOrigin``) where it matters.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import NewType

TriageId = NewType("TriageId", str)


class TriageVerdict(StrEnum):
    IN_SCOPE = "IN_SCOPE"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"


class MentionedObjectOrigin(StrEnum):
    """Who produced a mentioned-object entry: the AI's own extraction, or a
    staff correction/addition made afterwards via ``SyncTriageSearchTerms``."""

    AI = "AI"
    STAFF = "STAFF"


@dataclass(frozen=True, slots=True)
class MentionedObject:
    """One object/specimen name extracted from the question, kept in both
    languages so the catalogue can be searched in either — English and
    Portuguese are both required (a missing translation falls back to the
    other language, never left blank)."""

    english: str
    portuguese: str
    origin: MentionedObjectOrigin = MentionedObjectOrigin.AI


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
    catalogue"). ``languages_searched`` records which of "pt"/"en" were
    actually queried (English is skipped when identical to Portuguese)."""

    english: str
    portuguese: str
    hits: list[ObjectHitView]
    languages_searched: list[str] = field(default_factory=lambda: ["pt"])


@dataclass(slots=True)
class MessageTriage:
    """A triage run. ``verdict``/``is_visit_related`` are fixed at creation;
    ``mentioned_objects``/``object_matches``/``suggested_reply`` and the
    ``staff_override_*`` fields are revisable afterwards — see the module
    docstring."""

    id: TriageId
    question_id: str
    verdict: TriageVerdict
    is_visit_related: bool
    mentioned_objects: list[MentionedObject]
    object_matches: list[ObjectTriageMatch]
    suggested_reply: str | None
    llm_model: str
    created_at: datetime
    staff_override_verdict: TriageVerdict | None = None
    staff_override_at: datetime | None = None
    staff_override_by: str | None = None

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

    @property
    def effective_verdict(self) -> TriageVerdict:
        """The verdict that actually applies: the staff override if one was
        made, otherwise the AI's original classification."""
        return self.staff_override_verdict or self.verdict

    def override_verdict(self, verdict: TriageVerdict, *, by: str) -> None:
        """Record a staff correction of the scope verdict. Last-write-wins:
        calling this again simply replaces the previous override, with no
        conflict detection (accepted MVP limitation, see the refinements
        plan's "Decisões explícitas" section)."""
        self.staff_override_verdict = verdict
        self.staff_override_at = datetime.now(UTC)
        self.staff_override_by = by
