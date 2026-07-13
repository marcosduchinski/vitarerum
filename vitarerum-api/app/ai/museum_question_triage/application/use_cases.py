"""Museum-question triage application service.

Orchestrates the pipeline: load the question via the ACL → classify it
(in/out of scope + mentioned objects, each named in English and Portuguese) →
either draft an out-of-scope reply or search the catalogue in both languages
for each mentioned object → persist the run.
``execute`` takes an ``Input`` dataclass, per the repo-wide convention.
Authorization (``require_staff``) is enforced by the route handler, matching
``app.ai.museum_narrative``'s convention — not duplicated here.

Also hosts the two staff-review use cases added by the refinements plan
(docs/plans/museum-questions-ai-triage-refinements-plan.md):
``OverrideTriageVerdict`` (contest the scope verdict) and
``SyncTriageSearchTerms`` (edit/add/remove extracted search terms and
re-search only what changed).
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from io import StringIO
from typing import TYPE_CHECKING, Protocol

from app.ai.museum_question_triage.application.embedding_classifier import (
    EmbeddingClassificationResult,
)
from app.ai.museum_question_triage.domain.models import (
    ClassificationId,
    ClassificationOutcome,
    ClassificationQuality,
    ClassificationScoreSource,
    ClassificationStatus,
    ClassifierKind,
    HumanCategoryOutcome,
    MentionedObject,
    MentionedObjectOrigin,
    MessageClassification,
    MessageTriage,
    ObjectHitView,
    ObjectTriageMatch,
    TrainingExampleSource,
    TriageId,
    TriageVerdict,
    UseCategory,
    UseCategoryScore,
    UseCategoryTrainingExample,
)
from app.ai.museum_question_triage.domain.ports import (
    ClassificationNotFound,
    MessageClassificationRepository,
    ModelTimeout,
    ModelUnavailable,
    MuseumQuestionPort,
    ObjectSearchPort,
    QuestionNotFound,
    TriageModelPort,
    TriageNotFound,
    TriageNotInScope,
    TriageRepository,
    TriageTermValidationError,
    UseCategoryTrainingExampleRepository,
)

if TYPE_CHECKING:
    from app.identity.public import Actor


class UseCategoryEmbeddingClassifierPort(Protocol):
    async def classify(self, message: str) -> EmbeddingClassificationResult: ...

MAX_OBJECT_QUERIES = 3
# How many hits to fetch per language before merging — not a display cap (the
# UI paginates client-side over the full merged list); just a sane ceiling so
# a very common term can't pull in an unbounded number of rows.
SEARCH_FETCH_LIMIT_PER_LANGUAGE = 100
# Staff-edited search terms are a deliberate, explicit action per term, so
# MAX_OBJECT_QUERIES (which only bounds the AI's own automatic extraction)
# does not apply to them — but the whole list still needs a sanity ceiling so
# one request can't trigger dozens of catalogue searches at once.
MAX_STAFF_SEARCH_TERMS = 10
_MAX_TERM_FIELD_LENGTH = 200
USE_CATEGORY_CLASSIFIER_VERSION = "llm-use-category-v1"
EMBEDDING_USE_CATEGORY_CLASSIFIER_VERSION = "embedding-prototypes-v1"
CASCADE_USE_CATEGORY_CLASSIFIER_VERSION = "cascade-v1"
STAFF_USE_CATEGORY_CLASSIFIER_VERSION = "staff-reviewed-v1"
MAX_CALIBRATION_EXPORT_LIMIT = 500


def _normalized_message_hash(message: str) -> str:
    normalized = re.sub(r"\s+", " ", message.strip().casefold())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _scores_json(scores: list[UseCategoryScore]) -> str:
    return json.dumps(
        [
            {
                "category": score.category.value,
                "confidence": score.confidence,
                "source": score.source.value,
            }
            for score in scores
        ],
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def _score_by_category(scores: list[UseCategoryScore]) -> dict[str, UseCategoryScore]:
    return {score.category.value: score for score in scores}


def _normalize_use_categories(categories: list[UseCategory]) -> list[UseCategory]:
    seen: set[UseCategory] = set()
    normalized: list[UseCategory] = []
    for category in categories:
        if category in seen:
            continue
        seen.add(category)
        normalized.append(category)
    return sorted(normalized, key=lambda item: item.value)


def _assigned_categories(
    classification: MessageClassification | None,
) -> list[UseCategory]:
    if (
        classification is None
        or classification.status is not ClassificationStatus.COMPLETED
        or classification.outcome is not ClassificationOutcome.CATEGORIZED
    ):
        return []
    return _normalize_use_categories(
        [score.category for score in classification.assigned_categories]
    )


def _training_example_source(
    human_categories: list[UseCategory],
    llm_categories: list[UseCategory],
    embedding_categories: list[UseCategory],
) -> TrainingExampleSource:
    human = set(human_categories)
    llm = set(llm_categories)
    embedding = set(embedding_categories)
    if llm and human == llm:
        return TrainingExampleSource.LLM_ACCEPTED
    if llm or embedding:
        return TrainingExampleSource.HUMAN_CORRECTED
    return TrainingExampleSource.HUMAN_CREATED


def _cascade_margin(scores: list[UseCategoryScore]) -> float | None:
    if len(scores) < 2:
        return None
    ordered = sorted(scores, key=lambda score: score.confidence, reverse=True)
    return ordered[0].confidence - ordered[1].confidence


def _cascade_escalation_reasons(
    embedding_result: EmbeddingClassificationResult,
    *,
    high_threshold: float,
    margin_delta: float,
) -> list[str]:
    scores = embedding_result.classification.category_scores
    max_confidence = max((score.confidence for score in scores), default=0.0)
    margin = _cascade_margin(scores)
    reasons: list[str] = []
    if max_confidence < high_threshold:
        reasons.append("low_confidence")
    if margin is not None and margin < margin_delta:
        reasons.append("narrow_margin")
    if bool(embedding_result.metadata.get("would_escalate_due_to_length")):
        reasons.append("long_message")
    if embedding_result.metadata.get("uncertain_categories"):
        reasons.append("uncertain_category")
    return sorted(set(reasons))


def _combine_cascade_scores(
    embedding_scores: list[UseCategoryScore],
    llm_scores: list[UseCategoryScore],
    assigned_categories: list[UseCategoryScore],
) -> list[UseCategoryScore]:
    combined = _score_by_category(embedding_scores)
    for llm_score in llm_scores:
        combined[llm_score.category.value] = llm_score
    for assigned_score in assigned_categories:
        combined[assigned_score.category.value] = assigned_score
    return list(combined.values())


def _combine_cascade_assigned_categories(
    embedding_assigned: list[UseCategoryScore],
    llm_assigned: list[UseCategoryScore],
) -> list[UseCategoryScore]:
    combined = _score_by_category(embedding_assigned)
    for llm_score in llm_assigned:
        combined[llm_score.category.value] = llm_score
    return list(combined.values())


def _normalize_object_terms(pairs: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Trim, drop blank pairs, and deduplicate (case-insensitively, by the
    ``(portuguese, english)`` pair — not just Portuguese alone, since an
    imprecise translation could otherwise collapse two genuinely different
    objects that happen to share a Portuguese name). If only one language
    came back non-blank, the other falls back to it rather than being stored
    empty. Shared by the AI's own extraction (``_normalize_mentioned_objects``)
    and by staff-submitted term lists (``SyncTriageSearchTerms``) — this
    function only deals in plain text pairs, callers decide provenance."""
    seen: set[tuple[str, str]] = set()
    normalized: list[tuple[str, str]] = []
    for english_raw, portuguese_raw in pairs:
        english = english_raw.strip()
        portuguese = portuguese_raw.strip()
        if not english and not portuguese:
            continue
        english = english or portuguese
        portuguese = portuguese or english
        key = (portuguese.casefold(), english.casefold())
        if key in seen:
            continue
        seen.add(key)
        normalized.append((english, portuguese))
    return normalized


def _normalize_mentioned_objects(
    items: list[MentionedObject],
) -> list[MentionedObject]:
    """Apply ``_normalize_object_terms`` to the AI's raw extraction. Untrusted
    LLM output may otherwise contain blank/whitespace-only entries or
    repeats, wasting catalogue searches and polluting the persisted record."""
    pairs = _normalize_object_terms([(item.english, item.portuguese) for item in items])
    return [
        MentionedObject(english=english, portuguese=portuguese)
        for english, portuguese in pairs
    ]


def _merge_hits(
    primary: list[ObjectHitView], secondary: list[ObjectHitView]
) -> list[ObjectHitView]:
    """Merge two search result lists (Portuguese-first), dropping duplicates
    so a term matched by both languages isn't shown twice. Not truncated
    further here — each side is already bounded by
    ``SEARCH_FETCH_LIMIT_PER_LANGUAGE``, and the full merged list is what gets
    persisted; the UI paginates over it client-side. Keyed by collection +
    file + highlight (not just collection + file) so two distinct rows in the
    same source file — e.g. one matched by the Portuguese search, another by
    the English one — aren't mistaken for the same hit."""
    seen: set[tuple[str, str, str]] = set()
    merged: list[ObjectHitView] = []
    for hit in (*primary, *secondary):
        key = (hit.collection_id, hit.file_name, hit.highlight)
        if key in seen:
            continue
        seen.add(key)
        merged.append(hit)
    return merged


async def _search_both_languages(
    object_search: ObjectSearchPort, caller: Actor, *, english: str, portuguese: str
) -> tuple[list[ObjectHitView], list[str]]:
    """Search the catalogue in Portuguese (the primary language) and, if the
    English name differs, also in English — merging and deduplicating the
    results. Skips the second search when both names are identical (e.g. a
    proper noun the model didn't translate), to avoid a wasted query. Returns
    the merged hits alongside which language codes were actually searched
    (["pt"] or ["pt", "en"]), surfaced to staff as part of search-strategy
    transparency."""
    portuguese_hits = await object_search.search(
        caller, portuguese, SEARCH_FETCH_LIMIT_PER_LANGUAGE
    )
    if english.casefold() == portuguese.casefold():
        return portuguese_hits, ["pt"]
    english_hits = await object_search.search(
        caller, english, SEARCH_FETCH_LIMIT_PER_LANGUAGE
    )
    return _merge_hits(portuguese_hits, english_hits), ["pt", "en"]


@dataclass(frozen=True, slots=True)
class TriageMuseumQuestionInput:
    question_id: str
    caller: Actor


@dataclass(frozen=True, slots=True)
class CreatePendingUseCategoryClassificationInput:
    triage_id: str


@dataclass(frozen=True, slots=True)
class ClassifyPendingUseCategoryInput:
    classification_id: str


@dataclass(frozen=True, slots=True)
class CreatePendingEmbeddingUseCategoryClassificationInput:
    triage_id: str


@dataclass(frozen=True, slots=True)
class ClassifyPendingEmbeddingUseCategoryInput:
    classification_id: str


@dataclass(frozen=True, slots=True)
class CreatePendingCascadeUseCategoryClassificationInput:
    triage_id: str


@dataclass(frozen=True, slots=True)
class ClassifyPendingCascadeUseCategoryInput:
    classification_id: str


@dataclass(frozen=True, slots=True)
class ExportUseCategoryCalibrationInput:
    limit: int = 100


@dataclass(frozen=True, slots=True)
class GetLatestTriageInput:
    question_id: str


@dataclass(frozen=True, slots=True)
class OverrideTriageVerdictInput:
    question_id: str
    verdict: TriageVerdict
    caller: Actor


@dataclass(frozen=True, slots=True)
class SyncTriageSearchTermsInput:
    question_id: str
    terms: list[
        tuple[str, str]
    ]  # (english, portuguese) pairs, no origin — see routes.py
    caller: Actor


@dataclass(frozen=True, slots=True)
class SyncUseCategoriesInput:
    question_id: str
    categories: list[UseCategory]
    human_outcome: HumanCategoryOutcome
    caller: Actor


class TriageMuseumQuestion:
    def __init__(
        self,
        museum_question: MuseumQuestionPort,
        model: TriageModelPort,
        object_search: ObjectSearchPort,
        repository: TriageRepository,
        model_name: str,
    ) -> None:
        self._museum_question = museum_question
        self._model = model
        self._object_search = object_search
        self._repository = repository
        self._model_name = model_name

    async def execute(self, data: TriageMuseumQuestionInput) -> MessageTriage:
        question = await self._museum_question.get_summary(data.question_id)
        if question is None:
            raise QuestionNotFound(
                f"No museum question found with id {data.question_id!r}"
            )

        classification = await self._model.classify(question.message)
        verdict = (
            TriageVerdict.IN_SCOPE
            if classification.is_visit_related
            else TriageVerdict.OUT_OF_SCOPE
        )
        mentioned_objects = _normalize_mentioned_objects(
            classification.mentioned_objects
        )

        suggested_reply: str | None = None
        object_matches: list[ObjectTriageMatch] = []
        if verdict is TriageVerdict.OUT_OF_SCOPE:
            suggested_reply = await self._model.draft_out_of_scope_reply(
                question.message
            )
        else:
            for obj in mentioned_objects[:MAX_OBJECT_QUERIES]:
                hits, languages_searched = await _search_both_languages(
                    self._object_search,
                    data.caller,
                    english=obj.english,
                    portuguese=obj.portuguese,
                )
                object_matches.append(
                    ObjectTriageMatch(
                        english=obj.english,
                        portuguese=obj.portuguese,
                        hits=hits,
                        languages_searched=languages_searched,
                    )
                )

        record = MessageTriage.create(
            question_id=data.question_id,
            verdict=verdict,
            is_visit_related=classification.is_visit_related,
            mentioned_objects=mentioned_objects,
            object_matches=object_matches,
            suggested_reply=suggested_reply,
            llm_model=self._model_name,
        )
        await self._repository.add(record)
        return record


class CreatePendingUseCategoryClassification:
    def __init__(
        self,
        repository: MessageClassificationRepository,
        model_name: str,
        classifier_version: str = USE_CATEGORY_CLASSIFIER_VERSION,
    ) -> None:
        self._repository = repository
        self._model_name = model_name
        self._classifier_version = classifier_version

    async def execute(
        self, data: CreatePendingUseCategoryClassificationInput
    ) -> MessageClassification:
        triage_id = TriageId(data.triage_id)
        current = await self._repository.get_current_by_triage(
            triage_id, ClassifierKind.LLM
        )
        run_number = (current.run_number + 1) if current else 1
        if current is not None:
            await self._repository.supersede_current(
                triage_id, ClassifierKind.LLM, datetime.now(UTC)
            )
        classification = MessageClassification.pending(
            triage_id=triage_id,
            classifier_kind=ClassifierKind.LLM,
            classifier_model=self._model_name,
            classifier_version=self._classifier_version,
            run_number=run_number,
        )
        await self._repository.add(classification)
        return classification


class ClassifyPendingUseCategory:
    def __init__(
        self,
        museum_question: MuseumQuestionPort,
        model: TriageModelPort,
        triage_repository: TriageRepository,
        classification_repository: MessageClassificationRepository,
    ) -> None:
        self._museum_question = museum_question
        self._model = model
        self._triage_repository = triage_repository
        self._classification_repository = classification_repository

    async def execute(
        self, data: ClassifyPendingUseCategoryInput
    ) -> MessageClassification:
        classification = await self._classification_repository.get_by_id(
            ClassificationId(data.classification_id)
        )
        if classification is None:
            raise ClassificationNotFound(
                f"No classification found with id {data.classification_id!r}."
            )

        triage = await self._triage_repository.get_by_id(classification.triage_id)
        if triage is None:
            raise TriageNotFound(
                f"No triage found with id {classification.triage_id!r}."
            )

        question = await self._museum_question.get_summary(triage.question_id)
        if question is None:
            raise QuestionNotFound(
                f"No museum question found with id {triage.question_id!r}"
            )

        classified_at = datetime.now(UTC)
        try:
            result = await self._model.classify_use_categories(question.message)
        except (ModelUnavailable, ModelTimeout) as exc:
            updated = MessageClassification(
                id=classification.id,
                triage_id=classification.triage_id,
                classifier_kind=classification.classifier_kind,
                classifier_model=classification.classifier_model,
                classifier_version=classification.classifier_version,
                run_number=classification.run_number,
                superseded_at=classification.superseded_at,
                status=ClassificationStatus.FAILED,
                outcome=None,
                quality=None,
                category_scores=[],
                assigned_categories=[],
                error=str(exc),
                metadata=dict(classification.metadata),
                classified_at=classified_at,
                created_at=classification.created_at,
            )
        else:
            updated = MessageClassification(
                id=classification.id,
                triage_id=classification.triage_id,
                classifier_kind=classification.classifier_kind,
                classifier_model=classification.classifier_model,
                classifier_version=classification.classifier_version,
                run_number=classification.run_number,
                superseded_at=classification.superseded_at,
                status=ClassificationStatus.COMPLETED,
                outcome=result.outcome,
                quality=ClassificationQuality.FULL,
                category_scores=list(result.category_scores),
                assigned_categories=list(result.assigned_categories),
                error=None,
                metadata=dict(classification.metadata),
                classified_at=classified_at,
                created_at=classification.created_at,
            )

        await self._classification_repository.update(updated)
        return updated


class CreatePendingEmbeddingUseCategoryClassification:
    def __init__(
        self,
        repository: MessageClassificationRepository,
        model_name: str,
        classifier_version: str = EMBEDDING_USE_CATEGORY_CLASSIFIER_VERSION,
    ) -> None:
        self._repository = repository
        self._model_name = model_name
        self._classifier_version = classifier_version

    async def execute(
        self, data: CreatePendingEmbeddingUseCategoryClassificationInput
    ) -> MessageClassification:
        triage_id = TriageId(data.triage_id)
        current = await self._repository.get_current_by_triage(
            triage_id, ClassifierKind.EMBEDDING
        )
        run_number = (current.run_number + 1) if current else 1
        if current is not None:
            await self._repository.supersede_current(
                triage_id, ClassifierKind.EMBEDDING, datetime.now(UTC)
            )
        classification = MessageClassification.pending(
            triage_id=triage_id,
            classifier_kind=ClassifierKind.EMBEDDING,
            classifier_model=self._model_name,
            classifier_version=self._classifier_version,
            run_number=run_number,
        )
        await self._repository.add(classification)
        return classification


class ClassifyPendingEmbeddingUseCategory:
    def __init__(
        self,
        museum_question: MuseumQuestionPort,
        classifier: UseCategoryEmbeddingClassifierPort,
        triage_repository: TriageRepository,
        classification_repository: MessageClassificationRepository,
    ) -> None:
        self._museum_question = museum_question
        self._classifier = classifier
        self._triage_repository = triage_repository
        self._classification_repository = classification_repository

    async def execute(
        self, data: ClassifyPendingEmbeddingUseCategoryInput
    ) -> MessageClassification:
        classification = await self._classification_repository.get_by_id(
            ClassificationId(data.classification_id)
        )
        if classification is None:
            raise ClassificationNotFound(
                f"No classification found with id {data.classification_id!r}."
            )
        if classification.classifier_kind is not ClassifierKind.EMBEDDING:
            raise ClassificationNotFound(
                f"Classification {data.classification_id!r} is not an embedding run."
            )

        triage = await self._triage_repository.get_by_id(classification.triage_id)
        if triage is None:
            raise TriageNotFound(
                f"No triage found with id {classification.triage_id!r}."
            )

        question = await self._museum_question.get_summary(triage.question_id)
        if question is None:
            raise QuestionNotFound(
                f"No museum question found with id {triage.question_id!r}"
            )

        classified_at = datetime.now(UTC)
        try:
            result = await self._classifier.classify(question.message)
        except (ModelUnavailable, ModelTimeout) as exc:
            updated = MessageClassification(
                id=classification.id,
                triage_id=classification.triage_id,
                classifier_kind=classification.classifier_kind,
                classifier_model=classification.classifier_model,
                classifier_version=classification.classifier_version,
                run_number=classification.run_number,
                superseded_at=classification.superseded_at,
                status=ClassificationStatus.FAILED,
                outcome=None,
                quality=None,
                category_scores=[],
                assigned_categories=[],
                error=str(exc),
                metadata=dict(classification.metadata),
                classified_at=classified_at,
                created_at=classification.created_at,
            )
        else:
            updated = MessageClassification(
                id=classification.id,
                triage_id=classification.triage_id,
                classifier_kind=classification.classifier_kind,
                classifier_model=classification.classifier_model,
                classifier_version=classification.classifier_version,
                run_number=classification.run_number,
                superseded_at=classification.superseded_at,
                status=ClassificationStatus.COMPLETED,
                outcome=result.classification.outcome,
                quality=ClassificationQuality.FULL,
                category_scores=list(result.classification.category_scores),
                assigned_categories=list(result.classification.assigned_categories),
                error=None,
                metadata={**classification.metadata, **result.metadata},
                classified_at=classified_at,
                created_at=classification.created_at,
            )

        await self._classification_repository.update(updated)
        return updated


class CreatePendingCascadeUseCategoryClassification:
    def __init__(
        self,
        repository: MessageClassificationRepository,
        model_name: str,
        classifier_version: str = CASCADE_USE_CATEGORY_CLASSIFIER_VERSION,
    ) -> None:
        self._repository = repository
        self._model_name = model_name
        self._classifier_version = classifier_version

    async def execute(
        self, data: CreatePendingCascadeUseCategoryClassificationInput
    ) -> MessageClassification:
        triage_id = TriageId(data.triage_id)
        current = await self._repository.get_current_by_triage(
            triage_id, ClassifierKind.CASCADE
        )
        run_number = (current.run_number + 1) if current else 1
        if current is not None:
            await self._repository.supersede_current(
                triage_id, ClassifierKind.CASCADE, datetime.now(UTC)
            )
        classification = MessageClassification.pending(
            triage_id=triage_id,
            classifier_kind=ClassifierKind.CASCADE,
            classifier_model=self._model_name,
            classifier_version=self._classifier_version,
            run_number=run_number,
        )
        await self._repository.add(classification)
        return classification


class ClassifyPendingCascadeUseCategory:
    def __init__(
        self,
        museum_question: MuseumQuestionPort,
        embedding_classifier: UseCategoryEmbeddingClassifierPort,
        model: TriageModelPort,
        triage_repository: TriageRepository,
        classification_repository: MessageClassificationRepository,
        *,
        high_threshold: float,
        margin_delta: float,
    ) -> None:
        self._museum_question = museum_question
        self._embedding_classifier = embedding_classifier
        self._model = model
        self._triage_repository = triage_repository
        self._classification_repository = classification_repository
        self._high_threshold = high_threshold
        self._margin_delta = margin_delta

    async def execute(
        self, data: ClassifyPendingCascadeUseCategoryInput
    ) -> MessageClassification:
        classification = await self._classification_repository.get_by_id(
            ClassificationId(data.classification_id)
        )
        if classification is None:
            raise ClassificationNotFound(
                f"No classification found with id {data.classification_id!r}."
            )
        if classification.classifier_kind is not ClassifierKind.CASCADE:
            raise ClassificationNotFound(
                f"Classification {data.classification_id!r} is not a cascade run."
            )

        triage = await self._triage_repository.get_by_id(classification.triage_id)
        if triage is None:
            raise TriageNotFound(
                f"No triage found with id {classification.triage_id!r}."
            )

        question = await self._museum_question.get_summary(triage.question_id)
        if question is None:
            raise QuestionNotFound(
                f"No museum question found with id {triage.question_id!r}"
            )

        classified_at = datetime.now(UTC)
        try:
            embedding_result = await self._embedding_classifier.classify(
                question.message
            )
        except (ModelUnavailable, ModelTimeout) as exc:
            updated = MessageClassification(
                id=classification.id,
                triage_id=classification.triage_id,
                classifier_kind=classification.classifier_kind,
                classifier_model=classification.classifier_model,
                classifier_version=classification.classifier_version,
                run_number=classification.run_number,
                superseded_at=classification.superseded_at,
                status=ClassificationStatus.FAILED,
                outcome=None,
                quality=None,
                category_scores=[],
                assigned_categories=[],
                error=str(exc),
                metadata=dict(classification.metadata),
                classified_at=classified_at,
                created_at=classification.created_at,
            )
            await self._classification_repository.update(updated)
            return updated

        escalation_reasons = _cascade_escalation_reasons(
            embedding_result,
            high_threshold=self._high_threshold,
            margin_delta=self._margin_delta,
        )
        metadata = {
            **classification.metadata,
            **embedding_result.metadata,
            "cascade_high_threshold": self._high_threshold,
            "cascade_margin_delta": self._margin_delta,
            "escalation_reasons": escalation_reasons,
            "tier1_assigned_categories": [
                score.category.value
                for score in embedding_result.classification.assigned_categories
            ],
        }

        if not escalation_reasons:
            updated = MessageClassification(
                id=classification.id,
                triage_id=classification.triage_id,
                classifier_kind=classification.classifier_kind,
                classifier_model=classification.classifier_model,
                classifier_version=classification.classifier_version,
                run_number=classification.run_number,
                superseded_at=classification.superseded_at,
                status=ClassificationStatus.COMPLETED,
                outcome=embedding_result.classification.outcome,
                quality=ClassificationQuality.FULL,
                category_scores=list(embedding_result.classification.category_scores),
                assigned_categories=list(
                    embedding_result.classification.assigned_categories
                ),
                error=None,
                metadata={**metadata, "tier2_llm_used": False},
                classified_at=classified_at,
                created_at=classification.created_at,
            )
            await self._classification_repository.update(updated)
            return updated

        try:
            llm_result = await self._model.classify_use_categories(question.message)
        except (ModelUnavailable, ModelTimeout) as exc:
            updated = MessageClassification(
                id=classification.id,
                triage_id=classification.triage_id,
                classifier_kind=classification.classifier_kind,
                classifier_model=classification.classifier_model,
                classifier_version=classification.classifier_version,
                run_number=classification.run_number,
                superseded_at=classification.superseded_at,
                status=ClassificationStatus.COMPLETED,
                outcome=embedding_result.classification.outcome,
                quality=ClassificationQuality.DEGRADED,
                category_scores=list(embedding_result.classification.category_scores),
                assigned_categories=list(
                    embedding_result.classification.assigned_categories
                ),
                error=None,
                metadata={
                    **metadata,
                    "tier2_llm_used": True,
                    "fallback_reason": str(exc),
                },
                classified_at=classified_at,
                created_at=classification.created_at,
            )
            await self._classification_repository.update(updated)
            return updated

        assigned_categories = _combine_cascade_assigned_categories(
            list(embedding_result.classification.assigned_categories),
            list(llm_result.assigned_categories),
        )
        category_scores = _combine_cascade_scores(
            list(embedding_result.classification.category_scores),
            list(llm_result.category_scores),
            assigned_categories,
        )
        outcome = (
            ClassificationOutcome.CATEGORIZED
            if assigned_categories
            else ClassificationOutcome.UNCLEAR
        )
        updated = MessageClassification(
            id=classification.id,
            triage_id=classification.triage_id,
            classifier_kind=classification.classifier_kind,
            classifier_model=classification.classifier_model,
            classifier_version=classification.classifier_version,
            run_number=classification.run_number,
            superseded_at=classification.superseded_at,
            status=ClassificationStatus.COMPLETED,
            outcome=outcome,
            quality=ClassificationQuality.FULL,
            category_scores=category_scores,
            assigned_categories=assigned_categories,
            error=None,
            metadata={
                **metadata,
                "tier2_llm_used": True,
                "tier2_assigned_categories": [
                    score.category.value for score in llm_result.assigned_categories
                ],
            },
            classified_at=classified_at,
            created_at=classification.created_at,
        )
        await self._classification_repository.update(updated)
        return updated


class SyncUseCategories:
    """Persist the staff-reviewed category set as the current CASCADE line.

    This closes the cascade UI loop without changing the legacy binary verdict:
    manual category correction is a use-category classification revision, not a
    scope-verdict override.
    """

    def __init__(
        self,
        museum_question: MuseumQuestionPort,
        triage_repository: TriageRepository,
        classification_repository: MessageClassificationRepository,
        training_example_repository: UseCategoryTrainingExampleRepository,
        classifier_version: str = STAFF_USE_CATEGORY_CLASSIFIER_VERSION,
    ) -> None:
        self._museum_question = museum_question
        self._triage_repository = triage_repository
        self._classification_repository = classification_repository
        self._training_example_repository = training_example_repository
        self._classifier_version = classifier_version

    async def execute(self, data: SyncUseCategoriesInput) -> MessageClassification:
        triage = await self._triage_repository.get_latest_by_question(data.question_id)
        if triage is None:
            raise TriageNotFound(
                f"No triage has been run for question {data.question_id!r} yet."
            )
        question = await self._museum_question.get_summary(data.question_id)
        if question is None:
            raise QuestionNotFound(
                f"No museum question found with id {data.question_id!r}"
            )

        triage_id = triage.id
        llm = await self._classification_repository.get_current_by_triage(
            triage_id, ClassifierKind.LLM
        )
        embedding = await self._classification_repository.get_current_by_triage(
            triage_id, ClassifierKind.EMBEDDING
        )
        current = await self._classification_repository.get_current_by_triage(
            triage_id, ClassifierKind.CASCADE
        )
        run_number = (current.run_number + 1) if current else 1

        categories = _normalize_use_categories(data.categories)
        scores = [
            UseCategoryScore(
                category=category,
                confidence=1.0,
                source=ClassificationScoreSource.LLM,
            )
            for category in categories
        ]
        outcome = ClassificationOutcome(data.human_outcome.value)
        classified_at = datetime.now(UTC)

        existing_example = (
            await self._training_example_repository.get_current_by_triage(triage_id)
        )
        example_run_number = (
            existing_example.run_number + 1 if existing_example is not None else 1
        )
        source = _training_example_source(
            categories,
            _assigned_categories(llm),
            _assigned_categories(embedding),
        )
        training_example = UseCategoryTrainingExample.create(
            triage_id=triage_id,
            question_id=triage.question_id,
            run_number=example_run_number,
            human_outcome=data.human_outcome,
            human_categories=categories,
            llm_categories=_assigned_categories(llm),
            embedding_categories=_assigned_categories(embedding),
            source=source,
            reviewed_by=data.caller.email,
            reviewed_at=classified_at,
            message_hash=_normalized_message_hash(question.message),
        )

        classification = MessageClassification(
            id=ClassificationId(str(uuid.uuid4())),
            triage_id=triage_id,
            classifier_kind=ClassifierKind.CASCADE,
            classifier_model=None,
            classifier_version=self._classifier_version,
            run_number=run_number,
            superseded_at=None,
            status=ClassificationStatus.COMPLETED,
            outcome=outcome,
            quality=ClassificationQuality.FULL,
            category_scores=scores,
            assigned_categories=scores,
            error=None,
            metadata={
                "reviewed_by": data.caller.email,
                "reviewed_at": classified_at.isoformat(),
                "staff_reviewed": True,
                "training_example_id": training_example.id,
                "human_outcome": data.human_outcome.value,
            },
            classified_at=classified_at,
            created_at=classified_at,
        )
        await self._training_example_repository.add(training_example)
        if existing_example is not None:
            await self._training_example_repository.supersede_current(
                triage_id, classified_at, training_example.id
            )
        if current is not None:
            await self._classification_repository.supersede_current(
                triage_id, ClassifierKind.CASCADE, classified_at
            )
        await self._classification_repository.add(classification)
        return classification


class ExportUseCategoryCalibrationCsv:
    def __init__(
        self,
        museum_question: MuseumQuestionPort,
        triage_repository: TriageRepository,
        classification_repository: MessageClassificationRepository,
    ) -> None:
        self._museum_question = museum_question
        self._triage_repository = triage_repository
        self._classification_repository = classification_repository

    async def execute(self, data: ExportUseCategoryCalibrationInput) -> str:
        limit = max(1, min(data.limit, MAX_CALIBRATION_EXPORT_LIMIT))
        triages = await self._triage_repository.list_latest(limit=limit)
        output = StringIO()
        writer = csv.DictWriter(
            output,
            fieldnames=[
                "triage_id",
                "question_id",
                "internal_link",
                "question_status",
                "triage_created_at",
                "binary_effective_verdict",
                "message_hash_sha256",
                "llm_status",
                "llm_outcome",
                "llm_assigned_categories",
                "llm_category_scores",
                "embedding_status",
                "embedding_outcome",
                "embedding_assigned_categories",
                "embedding_category_scores",
                "embedding_metadata",
                "human_categories",
            ],
        )
        writer.writeheader()
        for triage in triages:
            question = await self._museum_question.get_summary(triage.question_id)
            if question is None:
                continue
            current_classifications = (
                await self._classification_repository.list_current_by_triage(triage.id)
            )
            by_kind = {
                classification.classifier_kind: classification
                for classification in current_classifications
            }
            llm = by_kind.get(ClassifierKind.LLM)
            embedding = by_kind.get(ClassifierKind.EMBEDDING)
            writer.writerow(
                {
                    "triage_id": triage.id,
                    "question_id": triage.question_id,
                    "internal_link": f"/p/museum-questions/{triage.question_id}",
                    "question_status": question.status,
                    "triage_created_at": triage.created_at.isoformat(),
                    "binary_effective_verdict": triage.effective_verdict.value,
                    "message_hash_sha256": _normalized_message_hash(question.message),
                    "llm_status": llm.status.value if llm else "NOT_REQUESTED",
                    "llm_outcome": llm.outcome.value if llm and llm.outcome else "",
                    "llm_assigned_categories": (
                        _scores_json(llm.assigned_categories) if llm else "[]"
                    ),
                    "llm_category_scores": (
                        _scores_json(llm.category_scores) if llm else "[]"
                    ),
                    "embedding_status": (
                        embedding.status.value if embedding else "NOT_REQUESTED"
                    ),
                    "embedding_outcome": (
                        embedding.outcome.value
                        if embedding and embedding.outcome
                        else ""
                    ),
                    "embedding_assigned_categories": (
                        _scores_json(embedding.assigned_categories)
                        if embedding
                        else "[]"
                    ),
                    "embedding_category_scores": (
                        _scores_json(embedding.category_scores) if embedding else "[]"
                    ),
                    "embedding_metadata": (
                        json.dumps(
                            embedding.metadata,
                            ensure_ascii=True,
                            sort_keys=True,
                            separators=(",", ":"),
                        )
                        if embedding
                        else "{}"
                    ),
                    "human_categories": "",
                }
            )
        return output.getvalue()


class GetLatestTriage:
    """Return the most recent stored triage for a question, or ``None`` if
    triage was never run."""

    def __init__(self, repository: TriageRepository) -> None:
        self._repository = repository

    async def execute(self, data: GetLatestTriageInput) -> MessageTriage | None:
        return await self._repository.get_latest_by_question(data.question_id)


class OverrideTriageVerdict:
    """Staff contesting the AI's scope verdict (checkpoint 1 of the
    refinements plan). Never rewrites ``verdict`` itself — only stamps
    ``staff_override_verdict``. If the effective verdict becomes
    OUT_OF_SCOPE and no reply was drafted yet (the AI's original run was
    IN_SCOPE, so it never ran ``draft_out_of_scope_reply``), one is generated
    now, lazily, and kept even if the staff flips back to IN_SCOPE later —
    the presentation layer decides whether to render it, not the domain."""

    def __init__(
        self,
        museum_question: MuseumQuestionPort,
        model: TriageModelPort,
        repository: TriageRepository,
    ) -> None:
        self._museum_question = museum_question
        self._model = model
        self._repository = repository

    async def execute(self, data: OverrideTriageVerdictInput) -> MessageTriage:
        triage = await self._repository.get_latest_by_question(data.question_id)
        if triage is None:
            raise TriageNotFound(
                f"No triage has been run for question {data.question_id!r} yet."
            )

        triage.override_verdict(data.verdict, by=data.caller.email)

        if (
            triage.effective_verdict is TriageVerdict.OUT_OF_SCOPE
            and triage.suggested_reply is None
        ):
            question = await self._museum_question.get_summary(data.question_id)
            if question is None:
                raise QuestionNotFound(
                    f"No museum question found with id {data.question_id!r}"
                )
            triage.suggested_reply = await self._model.draft_out_of_scope_reply(
                question.message
            )

        await self._repository.update(triage)
        return triage


class SyncTriageSearchTerms:
    """Staff editing/adding/removing extracted search terms (checkpoint 2 of
    the refinements plan) — a full reconciliation of the term list, not one
    endpoint per term. Diffs by the ``(portuguese, english)`` key against
    what's persisted: a key missing after the edit is dropped, a key present
    only after the edit is searched fresh (this covers both a genuinely new
    term and an edited one — editing changes the key, so there is no third
    "in-place edit" case to detect), and a key present in both is left
    untouched (no redundant re-search)."""

    def __init__(
        self,
        object_search: ObjectSearchPort,
        repository: TriageRepository,
    ) -> None:
        self._object_search = object_search
        self._repository = repository

    async def execute(self, data: SyncTriageSearchTermsInput) -> MessageTriage:
        triage = await self._repository.get_latest_by_question(data.question_id)
        if triage is None:
            raise TriageNotFound(
                f"No triage has been run for question {data.question_id!r} yet."
            )
        if triage.effective_verdict is not TriageVerdict.IN_SCOPE:
            raise TriageNotInScope(
                "Search terms can only be edited while the triage is in scope."
            )

        # Normalize (trim/drop-blank/dedupe) before validating: a field with
        # surrounding whitespace that fits within the limit once trimmed must
        # not be rejected for its raw, untrimmed length.
        normalized_pairs = _normalize_object_terms(data.terms)
        for english, portuguese in normalized_pairs:
            if (
                len(english) > _MAX_TERM_FIELD_LENGTH
                or len(portuguese) > _MAX_TERM_FIELD_LENGTH
            ):
                raise TriageTermValidationError(
                    f"Search term fields cannot exceed {_MAX_TERM_FIELD_LENGTH} "
                    "characters."
                )
        if len(normalized_pairs) > MAX_STAFF_SEARCH_TERMS:
            raise TriageTermValidationError(
                f"No more than {MAX_STAFF_SEARCH_TERMS} search terms are allowed."
            )

        existing_terms_by_key = {
            (obj.portuguese.casefold(), obj.english.casefold()): obj
            for obj in triage.mentioned_objects
        }
        existing_matches_by_key = {
            (match.portuguese.casefold(), match.english.casefold()): match
            for match in triage.object_matches
        }

        new_terms: list[MentionedObject] = []
        new_matches: list[ObjectTriageMatch] = []
        for english, portuguese in normalized_pairs:
            key = (portuguese.casefold(), english.casefold())
            existing_term = existing_terms_by_key.get(key)
            if existing_term is not None:
                new_terms.append(existing_term)
                existing_match = existing_matches_by_key.get(key)
                if existing_match is not None:
                    new_matches.append(existing_match)
                continue

            new_terms.append(
                MentionedObject(
                    english=english,
                    portuguese=portuguese,
                    origin=MentionedObjectOrigin.STAFF,
                )
            )
            hits, languages_searched = await _search_both_languages(
                self._object_search, data.caller, english=english, portuguese=portuguese
            )
            new_matches.append(
                ObjectTriageMatch(
                    english=english,
                    portuguese=portuguese,
                    hits=hits,
                    languages_searched=languages_searched,
                )
            )

        triage.mentioned_objects = new_terms
        triage.object_matches = new_matches
        await self._repository.update(triage)
        return triage
