from datetime import UTC, datetime

import pytest

from app.ai.museum_question_triage.domain.models import (
    ClassificationId,
    ClassificationOutcome,
    ClassificationQuality,
    ClassificationScoreSource,
    ClassificationStatus,
    ClassifierKind,
    HumanCategoryOutcome,
    InvalidMessageClassification,
    InvalidUseCategoryTrainingExample,
    MessageClassification,
    TrainingExampleId,
    TrainingExampleSource,
    TriageId,
    UseCategory,
    UseCategoryScore,
    UseCategoryTrainingExample,
)

_NOW = datetime(2026, 7, 10, 12, 0, tzinfo=UTC)


def _score(
    category: UseCategory = UseCategory.RESEARCH_PROJECTS,
    confidence: float = 0.91,
) -> UseCategoryScore:
    return UseCategoryScore(
        category=category,
        confidence=confidence,
        source=ClassificationScoreSource.LLM,
    )


def _classification(
    *,
    status: ClassificationStatus = ClassificationStatus.COMPLETED,
    outcome: ClassificationOutcome | None = ClassificationOutcome.CATEGORIZED,
    quality: ClassificationQuality | None = ClassificationQuality.FULL,
    category_scores: list[UseCategoryScore] | None = None,
    assigned_categories: list[UseCategoryScore] | None = None,
    error: str | None = None,
    classified_at: datetime | None = _NOW,
    run_number: int = 1,
) -> MessageClassification:
    scores = [_score()] if category_scores is None else category_scores
    assigned = [_score()] if assigned_categories is None else assigned_categories
    return MessageClassification(
        id=ClassificationId("classification-1"),
        triage_id=TriageId("triage-1"),
        classifier_kind=ClassifierKind.LLM,
        classifier_model="llama3.1:8b",
        classifier_version="llm-use-category-v1",
        run_number=run_number,
        superseded_at=None,
        status=status,
        outcome=outcome,
        quality=quality,
        category_scores=scores,
        assigned_categories=assigned,
        error=error,
        metadata={},
        classified_at=classified_at,
        created_at=_NOW,
    )


def _training_example(
    *,
    human_outcome: HumanCategoryOutcome = HumanCategoryOutcome.CATEGORIZED,
    human_categories: list[UseCategory] | None = None,
    llm_categories: list[UseCategory] | None = None,
    embedding_categories: list[UseCategory] | None = None,
    source: TrainingExampleSource = TrainingExampleSource.LLM_ACCEPTED,
    reviewed_by: str = "s@museum.pt",
    message_hash: str = "f" * 64,
) -> UseCategoryTrainingExample:
    categories = (
        [UseCategory.RESEARCH_PROJECTS]
        if human_categories is None
        else human_categories
    )
    llm = [UseCategory.RESEARCH_PROJECTS] if llm_categories is None else llm_categories
    return UseCategoryTrainingExample(
        id=TrainingExampleId("example-1"),
        triage_id=TriageId("triage-1"),
        question_id="q1",
        run_number=1,
        superseded_at=None,
        superseded_by_example_id=None,
        human_outcome=human_outcome,
        human_categories=categories,
        llm_categories=llm,
        embedding_categories=(
            [] if embedding_categories is None else embedding_categories
        ),
        source=source,
        reviewed_by=reviewed_by,
        reviewed_at=_NOW,
        message_hash=message_hash,
        active=True,
        notes=None,
        created_at=_NOW,
    )


def test_pending_factory_creates_a_valid_empty_classification() -> None:
    classification = MessageClassification.pending(
        triage_id=TriageId("triage-1"),
        classifier_kind=ClassifierKind.LLM,
        classifier_model="llama3.1:8b",
        classifier_version="llm-use-category-v1",
    )

    assert classification.status is ClassificationStatus.PENDING
    assert classification.outcome is None
    assert classification.quality is None
    assert classification.category_scores == []
    assert classification.assigned_categories == []
    assert classification.classified_at is None
    assert classification.run_number == 1


def test_pending_rejects_result_fields() -> None:
    with pytest.raises(InvalidMessageClassification):
        _classification(
            status=ClassificationStatus.PENDING,
            outcome=ClassificationOutcome.CATEGORIZED,
            quality=None,
            category_scores=[],
            assigned_categories=[],
            classified_at=None,
        )


def test_completed_requires_outcome_quality_and_classified_at() -> None:
    with pytest.raises(InvalidMessageClassification):
        _classification(outcome=None)

    with pytest.raises(InvalidMessageClassification):
        _classification(quality=None)

    with pytest.raises(InvalidMessageClassification):
        _classification(classified_at=None)


def test_failed_requires_error_and_rejects_outcome() -> None:
    with pytest.raises(InvalidMessageClassification):
        _classification(
            status=ClassificationStatus.FAILED,
            outcome=ClassificationOutcome.CATEGORIZED,
            quality=None,
            category_scores=[],
            assigned_categories=[],
            error="model unavailable",
        )

    with pytest.raises(InvalidMessageClassification):
        _classification(
            status=ClassificationStatus.FAILED,
            outcome=None,
            quality=None,
            category_scores=[],
            assigned_categories=[],
            error=None,
        )


def test_unclear_rejects_assigned_categories() -> None:
    with pytest.raises(InvalidMessageClassification):
        _classification(
            outcome=ClassificationOutcome.UNCLEAR,
            category_scores=[_score()],
            assigned_categories=[_score()],
        )


def test_categorized_requires_assigned_categories() -> None:
    with pytest.raises(InvalidMessageClassification):
        _classification(assigned_categories=[])


def test_assigned_categories_must_match_category_scores_exactly() -> None:
    with pytest.raises(InvalidMessageClassification):
        _classification(
            category_scores=[_score(confidence=0.91)],
            assigned_categories=[_score(confidence=0.72)],
        )

    with pytest.raises(InvalidMessageClassification):
        _classification(
            category_scores=[_score(UseCategory.RESEARCH_PROJECTS)],
            assigned_categories=[_score(UseCategory.FILMING)],
        )


def test_rejects_confidence_outside_unit_interval() -> None:
    with pytest.raises(InvalidMessageClassification):
        _score(confidence=1.01)

    with pytest.raises(InvalidMessageClassification):
        _score(confidence=-0.01)


def test_rejects_duplicate_category_scores() -> None:
    with pytest.raises(InvalidMessageClassification):
        _classification(
            category_scores=[
                _score(UseCategory.RESEARCH_PROJECTS, confidence=0.91),
                _score(UseCategory.RESEARCH_PROJECTS, confidence=0.74),
            ],
            assigned_categories=[
                _score(UseCategory.RESEARCH_PROJECTS, confidence=0.91)
            ],
        )


def test_sorts_category_scores_deterministically() -> None:
    classification = _classification(
        category_scores=[
            _score(UseCategory.FILMING, confidence=0.7),
            _score(UseCategory.RESEARCH_PROJECTS, confidence=0.91),
            _score(UseCategory.EXHIBITION, confidence=0.91),
        ],
        assigned_categories=[
            _score(UseCategory.FILMING, confidence=0.7),
            _score(UseCategory.RESEARCH_PROJECTS, confidence=0.91),
            _score(UseCategory.EXHIBITION, confidence=0.91),
        ],
    )

    assert [score.category for score in classification.category_scores] == [
        UseCategory.EXHIBITION,
        UseCategory.RESEARCH_PROJECTS,
        UseCategory.FILMING,
    ]
    assert [score.category for score in classification.assigned_categories] == [
        UseCategory.EXHIBITION,
        UseCategory.RESEARCH_PROJECTS,
        UseCategory.FILMING,
    ]


def test_run_number_starts_at_one() -> None:
    with pytest.raises(InvalidMessageClassification):
        _classification(run_number=0)


def test_training_example_requires_categories_for_categorized() -> None:
    with pytest.raises(InvalidUseCategoryTrainingExample):
        _training_example(
            human_outcome=HumanCategoryOutcome.CATEGORIZED,
            human_categories=[],
            llm_categories=[],
            source=TrainingExampleSource.HUMAN_CREATED,
        )


def test_training_example_unclear_requires_empty_categories() -> None:
    with pytest.raises(InvalidUseCategoryTrainingExample):
        _training_example(
            human_outcome=HumanCategoryOutcome.UNCLEAR,
            human_categories=[UseCategory.RESEARCH_PROJECTS],
        )


def test_training_example_rejects_duplicate_human_categories() -> None:
    with pytest.raises(InvalidUseCategoryTrainingExample):
        _training_example(
            human_categories=[
                UseCategory.RESEARCH_PROJECTS,
                UseCategory.RESEARCH_PROJECTS,
            ]
        )


def test_training_example_requires_review_audit_fields() -> None:
    with pytest.raises(InvalidUseCategoryTrainingExample):
        _training_example(reviewed_by="")

    with pytest.raises(InvalidUseCategoryTrainingExample):
        _training_example(message_hash="")


def test_training_example_llm_accepted_must_match_llm_categories() -> None:
    with pytest.raises(InvalidUseCategoryTrainingExample):
        _training_example(
            human_categories=[UseCategory.RESEARCH_PROJECTS],
            llm_categories=[UseCategory.EXHIBITION],
            source=TrainingExampleSource.LLM_ACCEPTED,
        )


def test_training_example_human_created_requires_no_suggestions() -> None:
    with pytest.raises(InvalidUseCategoryTrainingExample):
        _training_example(
            human_categories=[UseCategory.RESEARCH_PROJECTS],
            llm_categories=[UseCategory.EXHIBITION],
            source=TrainingExampleSource.HUMAN_CREATED,
        )


def test_training_example_human_corrected_accepts_embedding_acceptance() -> None:
    example = _training_example(
        human_categories=[UseCategory.RESEARCH_PROJECTS],
        llm_categories=[UseCategory.EXHIBITION],
        embedding_categories=[UseCategory.RESEARCH_PROJECTS],
        source=TrainingExampleSource.HUMAN_CORRECTED,
    )

    assert example.source is TrainingExampleSource.HUMAN_CORRECTED
