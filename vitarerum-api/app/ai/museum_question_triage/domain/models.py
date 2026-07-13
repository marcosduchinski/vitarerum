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
TrainingExampleId = NewType("TrainingExampleId", str)


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


class HumanCategoryOutcome(StrEnum):
    CATEGORIZED = "CATEGORIZED"
    UNCLEAR = "UNCLEAR"


class TrainingExampleSource(StrEnum):
    LLM_ACCEPTED = "LLM_ACCEPTED"
    HUMAN_CORRECTED = "HUMAN_CORRECTED"
    HUMAN_CREATED = "HUMAN_CREATED"


class InvalidMessageClassification(Exception):
    """A use-category classification violates a domain invariant."""


class InvalidUseCategoryTrainingExample(Exception):
    """A staff-reviewed training example violates a domain invariant."""


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


@dataclass(slots=True)
class UseCategoryTrainingExample:
    """A human-reviewed category label usable for embedding calibration.

    It is deliberately separate from the operational CASCADE classification
    row so bad examples can be withdrawn without rewriting classifier history.
    """

    id: TrainingExampleId
    triage_id: TriageId
    question_id: str
    run_number: int
    superseded_at: datetime | None
    superseded_by_example_id: TrainingExampleId | None
    human_outcome: HumanCategoryOutcome
    human_categories: list[UseCategory]
    llm_categories: list[UseCategory]
    embedding_categories: list[UseCategory]
    source: TrainingExampleSource
    reviewed_by: str
    reviewed_at: datetime
    message_hash: str
    active: bool
    notes: str | None
    created_at: datetime

    def __post_init__(self) -> None:
        self.human_categories = _sorted_categories(self.human_categories)
        self.llm_categories = _sorted_categories(self.llm_categories)
        self.embedding_categories = _sorted_categories(self.embedding_categories)
        if self.run_number < 1:
            raise InvalidUseCategoryTrainingExample("run_number must start at 1.")
        if not self.question_id.strip():
            raise InvalidUseCategoryTrainingExample("question_id is required.")
        if not self.reviewed_by.strip():
            raise InvalidUseCategoryTrainingExample("reviewed_by is required.")
        if not self.message_hash.strip():
            raise InvalidUseCategoryTrainingExample("message_hash is required.")
        _reject_duplicate_categories(self.human_categories, "human_categories")
        _reject_duplicate_categories(self.llm_categories, "llm_categories")
        _reject_duplicate_categories(self.embedding_categories, "embedding_categories")
        if (
            self.human_outcome is HumanCategoryOutcome.CATEGORIZED
            and not self.human_categories
        ):
            raise InvalidUseCategoryTrainingExample(
                "CATEGORIZED training examples require human categories."
            )
        if (
            self.human_outcome is HumanCategoryOutcome.UNCLEAR
            and self.human_categories
        ):
            raise InvalidUseCategoryTrainingExample(
                "UNCLEAR training examples cannot have human categories."
            )
        self._validate_source()

    def _validate_source(self) -> None:
        human = set(self.human_categories)
        llm = set(self.llm_categories)
        embedding = set(self.embedding_categories)
        if self.source is TrainingExampleSource.LLM_ACCEPTED and human != llm:
            raise InvalidUseCategoryTrainingExample(
                "LLM_ACCEPTED requires human categories to match LLM categories."
            )
        if self.source is TrainingExampleSource.HUMAN_CORRECTED:
            if not llm and not embedding:
                raise InvalidUseCategoryTrainingExample(
                    "HUMAN_CORRECTED requires a previous LLM or embedding suggestion."
                )
            if llm and human == llm:
                raise InvalidUseCategoryTrainingExample(
                    "Human categories matching LLM categories must use LLM_ACCEPTED."
                )
        if self.source is TrainingExampleSource.HUMAN_CREATED and (llm or embedding):
            raise InvalidUseCategoryTrainingExample(
                "HUMAN_CREATED requires no valid LLM or embedding suggestion."
            )

    @classmethod
    def create(
        cls,
        *,
        triage_id: TriageId,
        question_id: str,
        run_number: int,
        human_outcome: HumanCategoryOutcome,
        human_categories: list[UseCategory],
        llm_categories: list[UseCategory],
        embedding_categories: list[UseCategory],
        source: TrainingExampleSource,
        reviewed_by: str,
        reviewed_at: datetime,
        message_hash: str,
        active: bool = True,
        notes: str | None = None,
    ) -> UseCategoryTrainingExample:
        return cls(
            id=TrainingExampleId(str(uuid.uuid4())),
            triage_id=triage_id,
            question_id=question_id,
            run_number=run_number,
            superseded_at=None,
            superseded_by_example_id=None,
            human_outcome=human_outcome,
            human_categories=human_categories,
            llm_categories=llm_categories,
            embedding_categories=embedding_categories,
            source=source,
            reviewed_by=reviewed_by,
            reviewed_at=reviewed_at,
            message_hash=message_hash,
            active=active,
            notes=notes,
            created_at=reviewed_at,
        )


def _category_sort_key(category: UseCategory) -> str:
    return category.value


def _sorted_categories(categories: list[UseCategory]) -> list[UseCategory]:
    return sorted(categories, key=_category_sort_key)


def _reject_duplicate_categories(
    categories: list[UseCategory], field_name: str
) -> None:
    if len(set(categories)) != len(categories):
        raise InvalidUseCategoryTrainingExample(
            f"{field_name} cannot contain duplicate categories."
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
