import pytest

from app.ai.museum_question_triage.application.embedding_classifier import (
    EmbeddingThresholds,
    UseCategoryEmbeddingClassifier,
    cosine_similarity,
    load_use_category_prototypes,
)
from app.ai.museum_question_triage.domain.models import (
    ClassificationOutcome,
    ClassificationScoreSource,
    UseCategory,
)


class _FakeEmbedding:
    def __init__(self, vectors: dict[str, list[float]]) -> None:
        self._vectors = vectors
        self.calls: list[str] = []

    async def embed(self, text: str) -> list[float]:
        self.calls.append(text)
        return self._vectors[text]

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        self.calls.extend(texts)
        return [self._vectors[text] for text in texts]


def test_loads_versioned_prototypes_for_every_category() -> None:
    prototypes = load_use_category_prototypes()

    assert set(prototypes) == set(UseCategory)
    assert all(examples for examples in prototypes.values())


def test_cosine_similarity_bounds_result() -> None:
    assert cosine_similarity([1, 0], [1, 0]) == 1
    assert cosine_similarity([1, 0], [0, 1]) == 0


async def test_embedding_classifier_assigns_high_confidence_categories() -> None:
    message = "I want to study the meteorite collection"
    prototypes = {
        UseCategory.RESEARCH_PROJECTS: ["study specimens"],
        UseCategory.FILMING: ["film a documentary"],
    }
    embedding = _FakeEmbedding(
        {
            message: [1, 0],
            "study specimens": [0.95, 0.05],
            "film a documentary": [0, 1],
        }
    )
    classifier = UseCategoryEmbeddingClassifier(
        embedding,
        EmbeddingThresholds(
            low=0.4,
            high=0.8,
            profile_version="test-profile",
            long_message_words=3,
        ),
        prototypes,
    )

    result = await classifier.classify(message)

    assert result.classification.outcome is ClassificationOutcome.CATEGORIZED
    assert result.classification.assigned_categories[0].category is (
        UseCategory.RESEARCH_PROJECTS
    )
    assert result.classification.assigned_categories[0].source is (
        ClassificationScoreSource.EMBEDDING
    )
    assert result.metadata["threshold_profile"] == "test-profile"
    assert result.metadata["would_escalate_due_to_length"] is True
    assert result.metadata["aggregation"] == "max"
    assert embedding.calls == [message, "film a documentary", "study specimens"]


async def test_embedding_classifier_returns_unclear_without_high_score() -> None:
    message = "unrelated text"
    classifier = UseCategoryEmbeddingClassifier(
        _FakeEmbedding(
            {
                message: [1, 0],
                "study specimens": [0.5, 0.5],
            }
        ),
        EmbeddingThresholds(
            low=0.4,
            high=0.9,
            profile_version="test-profile",
            long_message_words=80,
        ),
        {UseCategory.RESEARCH_PROJECTS: ["study specimens"]},
    )

    result = await classifier.classify(message)

    assert result.classification.outcome is ClassificationOutcome.UNCLEAR
    assert result.classification.assigned_categories == []
    assert result.metadata["uncertain_categories"] == ["RESEARCH_PROJECTS"]


def test_thresholds_reject_invalid_order() -> None:
    with pytest.raises(ValueError):
        EmbeddingThresholds(
            low=0.9,
            high=0.4,
            profile_version="bad",
            long_message_words=80,
        )
