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
ClassificationId = NewType("ClassificationId", str)


class TriageVerdict(StrEnum):
    IN_SCOPE = "IN_SCOPE"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"


class MentionedObjectOrigin(StrEnum):
    """Who produced a mentioned-object entry: the AI's own extraction, or a
    staff correction/addition made afterwards via ``SyncTriageSearchTerms``."""

    AI = "AI"
    STAFF = "STAFF"


class UseCategory(StrEnum):
    EXHIBITION = "EXHIBITION"
    PUBLISHING_IMAGES = "PUBLISHING_IMAGES"
    LEARNING_EVENTS = "LEARNING_EVENTS"
    ANSWERING_ENQUIRIES = "ANSWERING_ENQUIRIES"
    RESEARCH_PROJECTS = "RESEARCH_PROJECTS"
    OPERATING_MACHINERY = "OPERATING_MACHINERY"
    PLAYING_INSTRUMENTS = "PLAYING_INSTRUMENTS"
    FILMING = "FILMING"
    INSPIRING_NEW_WORK = "INSPIRING_NEW_WORK"


class ClassificationOutcome(StrEnum):
    CATEGORIZED = "CATEGORIZED"
    UNCLEAR = "UNCLEAR"


class ClassificationStatus(StrEnum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ClassifierKind(StrEnum):
    LLM = "LLM"
    EMBEDDING = "EMBEDDING"
    CASCADE = "CASCADE"


class ClassificationQuality(StrEnum):
    FULL = "FULL"
    DEGRADED = "DEGRADED"


class ClassificationScoreSource(StrEnum):
    LLM = "LLM"
    EMBEDDING = "EMBEDDING"


class InvalidMessageClassification(Exception):
    """A use-category classification violates a domain invariant."""


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
class UseCategoryClassification:
    """Structured output of the use-category classification model call."""

    outcome: ClassificationOutcome
    category_scores: list[UseCategoryScore]
    assigned_categories: list[UseCategoryScore]

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "category_scores", _sorted_scores(self.category_scores)
        )
        object.__setattr__(
            self, "assigned_categories", _sorted_scores(self.assigned_categories)
        )
        if (
            self.outcome is ClassificationOutcome.CATEGORIZED
            and not self.assigned_categories
        ):
            raise InvalidMessageClassification(
                "CATEGORIZED classifications require assigned categories."
            )
        if (
            self.outcome is ClassificationOutcome.UNCLEAR
            and self.assigned_categories
        ):
            raise InvalidMessageClassification(
                "UNCLEAR classifications cannot have assigned categories."
            )
        seen: set[UseCategory] = set()
        for score in self.category_scores:
            if score.category in seen:
                raise InvalidMessageClassification(
                    "category_scores cannot contain duplicate categories."
                )
            seen.add(score.category)
        scores_by_category = {score.category: score for score in self.category_scores}
        for assigned in self.assigned_categories:
            if scores_by_category.get(assigned.category) != assigned:
                raise InvalidMessageClassification(
                    "Assigned categories must exactly match category_scores entries."
                )


@dataclass(frozen=True, slots=True)
class UseCategoryScore:
    category: UseCategory
    confidence: float
    source: ClassificationScoreSource

    def __post_init__(self) -> None:
        if not 0 <= self.confidence <= 1:
            raise InvalidMessageClassification("Confidence must be between 0 and 1.")


def _score_sort_key(score: UseCategoryScore) -> tuple[float, str, str]:
    return (-score.confidence, score.category.value, score.source.value)


def _sorted_scores(scores: list[UseCategoryScore]) -> list[UseCategoryScore]:
    return sorted(scores, key=_score_sort_key)


@dataclass(slots=True)
class MessageClassification:
    """One execution of a use-category classifier for a stored triage run."""

    id: ClassificationId
    triage_id: TriageId
    classifier_kind: ClassifierKind
    classifier_model: str | None
    classifier_version: str | None
    run_number: int
    superseded_at: datetime | None
    status: ClassificationStatus
    outcome: ClassificationOutcome | None
    quality: ClassificationQuality | None
    category_scores: list[UseCategoryScore]
    assigned_categories: list[UseCategoryScore]
    error: str | None
    metadata: dict[str, object]
    classified_at: datetime | None
    created_at: datetime

    def __post_init__(self) -> None:
        self.category_scores = _sorted_scores(self.category_scores)
        self.assigned_categories = _sorted_scores(self.assigned_categories)
        if self.run_number < 1:
            raise InvalidMessageClassification("run_number must start at 1.")
        self._validate_status_fields()
        self._validate_scores()

    @classmethod
    def pending(
        cls,
        *,
        triage_id: TriageId,
        classifier_kind: ClassifierKind,
        classifier_model: str | None,
        classifier_version: str | None,
        run_number: int = 1,
    ) -> MessageClassification:
        return cls(
            id=ClassificationId(str(uuid.uuid4())),
            triage_id=triage_id,
            classifier_kind=classifier_kind,
            classifier_model=classifier_model,
            classifier_version=classifier_version,
            run_number=run_number,
            superseded_at=None,
            status=ClassificationStatus.PENDING,
            outcome=None,
            quality=None,
            category_scores=[],
            assigned_categories=[],
            error=None,
            metadata={},
            classified_at=None,
            created_at=datetime.now(UTC),
        )

    def _validate_status_fields(self) -> None:
        if self.status is ClassificationStatus.PENDING:
            if self.outcome or self.quality or self.error or self.classified_at:
                raise InvalidMessageClassification(
                    "PENDING classifications cannot have result fields."
                )
            return

        if self.status is ClassificationStatus.COMPLETED:
            if (
                self.outcome is None
                or self.quality is None
                or self.classified_at is None
            ):
                raise InvalidMessageClassification(
                    "COMPLETED classifications require outcome, quality, "
                    "and classified_at."
                )
            if self.error is not None:
                raise InvalidMessageClassification(
                    "COMPLETED classifications cannot have an error."
                )
            return

        if self.status is ClassificationStatus.FAILED:
            if self.outcome or self.quality:
                raise InvalidMessageClassification(
                    "FAILED classifications cannot have outcome or quality."
                )
            if self.error is None or self.classified_at is None:
                raise InvalidMessageClassification(
                    "FAILED classifications require error and classified_at."
                )

    def _validate_scores(self) -> None:
        seen: set[UseCategory] = set()
        for score in self.category_scores:
            if score.category in seen:
                raise InvalidMessageClassification(
                    "category_scores cannot contain duplicate categories."
                )
            seen.add(score.category)

        if self.status is not ClassificationStatus.COMPLETED:
            if self.category_scores or self.assigned_categories:
                raise InvalidMessageClassification(
                    "Only COMPLETED classifications can have category scores."
                )
            return

        if (
            self.outcome is ClassificationOutcome.CATEGORIZED
            and not self.assigned_categories
        ):
            raise InvalidMessageClassification(
                "CATEGORIZED classifications require assigned categories."
            )
        if (
            self.outcome is ClassificationOutcome.UNCLEAR
            and self.assigned_categories
        ):
            raise InvalidMessageClassification(
                "UNCLEAR classifications cannot have assigned categories."
            )

        scores_by_category = {score.category: score for score in self.category_scores}
        for assigned in self.assigned_categories:
            if scores_by_category.get(assigned.category) != assigned:
                raise InvalidMessageClassification(
                    "Assigned categories must exactly match category_scores entries."
                )


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
