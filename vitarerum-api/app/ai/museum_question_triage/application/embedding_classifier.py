from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from app.ai.museum_question_triage.domain.models import (
    ClassificationOutcome,
    ClassificationScoreSource,
    EmbeddingPrototypeAggregation,
    EmbeddingPrototypeVersion,
    UseCategory,
    UseCategoryClassification,
    UseCategoryScore,
)
from app.ai.museum_question_triage.domain.ports import (
    EmbeddingClassifierPort,
    EmbeddingPrototypeVersionRepository,
)

_PROTOTYPES_PATH = Path(__file__).with_name("use_category_prototypes.json")
EmbeddingPrototypeSource = Literal["PROMOTED", "JSON_SEED"]


@dataclass(frozen=True, slots=True)
class EmbeddingThresholds:
    low: float
    high: float
    profile_version: str
    long_message_words: int

    def __post_init__(self) -> None:
        if not 0 <= self.low <= self.high <= 1:
            raise ValueError("Embedding thresholds must satisfy 0 <= low <= high <= 1.")
        if self.long_message_words < 1:
            raise ValueError("long_message_words must be positive.")


@dataclass(frozen=True, slots=True)
class EmbeddingClassificationResult:
    classification: UseCategoryClassification
    metadata: dict[str, object]


@dataclass(frozen=True, slots=True)
class PersistedEmbeddingPrototypes:
    version: str
    aggregation_method: EmbeddingPrototypeAggregation
    prototypes: dict[UseCategory, list[list[float]]]
    metrics: dict[str, object]


def persisted_prototypes_from_version(
    version: EmbeddingPrototypeVersion,
) -> PersistedEmbeddingPrototypes:
    return PersistedEmbeddingPrototypes(
        version=version.version,
        aggregation_method=version.aggregation_method,
        prototypes=version.prototypes,
        metrics=version.metrics,
    )


async def build_use_category_embedding_classifier(
    embedding: EmbeddingClassifierPort,
    thresholds: EmbeddingThresholds,
    prototype_repository: EmbeddingPrototypeVersionRepository,
    *,
    prototype_source: EmbeddingPrototypeSource,
) -> UseCategoryEmbeddingClassifier:
    promoted_version = (
        await prototype_repository.get_promoted()
        if prototype_source == "PROMOTED"
        else None
    )
    return UseCategoryEmbeddingClassifier(
        embedding,
        thresholds,
        persisted_prototypes=(
            persisted_prototypes_from_version(promoted_version)
            if promoted_version is not None
            else None
        ),
    )


def load_use_category_prototypes(
    path: Path = _PROTOTYPES_PATH,
) -> dict[UseCategory, list[str]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    prototypes: dict[UseCategory, list[str]] = {}
    for category_value, examples in raw.items():
        category = UseCategory(category_value)
        if not isinstance(examples, list) or not examples:
            raise ValueError(f"Use category {category.value} must define examples.")
        normalized = [
            str(example).strip() for example in examples if str(example).strip()
        ]
        if not normalized:
            raise ValueError(f"Use category {category.value} has no usable examples.")
        prototypes[category] = normalized
    missing = set(UseCategory) - set(prototypes)
    if missing:
        missing_values = ", ".join(sorted(category.value for category in missing))
        raise ValueError(f"Missing use category prototypes: {missing_values}")
    return prototypes


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        raise ValueError("Embedding vectors must be non-empty and have equal length.")
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return max(0.0, min(1.0, dot / (left_norm * right_norm)))


def _word_count(text: str) -> int:
    return len([part for part in text.split() if part.strip()])


class UseCategoryEmbeddingClassifier:
    def __init__(
        self,
        embedding: EmbeddingClassifierPort,
        thresholds: EmbeddingThresholds,
        prototypes: dict[UseCategory, list[str]] | None = None,
        persisted_prototypes: PersistedEmbeddingPrototypes | None = None,
    ) -> None:
        self._embedding = embedding
        self._thresholds = thresholds
        self._persisted_prototypes = persisted_prototypes
        self._prototypes = (
            prototypes
            if prototypes is not None
            else (
                {}
                if persisted_prototypes is not None
                else load_use_category_prototypes()
            )
        )

    async def classify(self, message: str) -> EmbeddingClassificationResult:
        if self._persisted_prototypes is not None:
            vectors = await self._embedding.embed_many([message])
            message_vector = vectors[0]
            return self._classify_from_vectors(message, message_vector)

        return await self._classify_from_text_prototypes(message)

    async def _classify_from_text_prototypes(
        self, message: str
    ) -> EmbeddingClassificationResult:
        prototype_items = [
            (category, prototype)
            for category in sorted(self._prototypes, key=lambda item: item.value)
            for prototype in self._prototypes[category]
        ]
        vectors = await self._embedding.embed_many(
            [message, *[prototype for _, prototype in prototype_items]]
        )
        message_vector = vectors[0]
        prototype_vectors = vectors[1:]
        vectors_by_category: dict[UseCategory, list[list[float]]] = {
            category: [] for category in self._prototypes
        }
        for (category, _prototype), prototype_vector in zip(
            prototype_items, prototype_vectors, strict=True
        ):
            vectors_by_category[category].append(prototype_vector)
        return self._classify_from_vectors(message, message_vector, vectors_by_category)

    def _classify_from_vectors(
        self,
        message: str,
        message_vector: list[float],
        vectors_by_category: dict[UseCategory, list[list[float]]] | None = None,
    ) -> EmbeddingClassificationResult:
        persisted = self._persisted_prototypes
        if persisted is not None:
            vectors_by_category = persisted.prototypes
        if vectors_by_category is None:
            raise ValueError("Prototype vectors are required.")

        scores: list[UseCategoryScore] = []
        raw_scores: dict[str, float] = {}
        raw_mean_scores: dict[str, float] = {}
        raw_max_example_scores: dict[str, float] = {}

        for category in sorted(vectors_by_category, key=lambda item: item.value):
            confidence = self._category_confidence(
                message_vector,
                vectors_by_category[category],
                persisted.aggregation_method if persisted is not None else None,
                raw_mean_scores,
                raw_max_example_scores,
                category,
            )
            raw_scores[category.value] = confidence
            scores.append(
                UseCategoryScore(
                    category=category,
                    confidence=confidence,
                    source=ClassificationScoreSource.EMBEDDING,
                )
            )

        assigned = [
            score for score in scores if score.confidence >= self._thresholds.high
        ]
        uncertain = [
            score.category.value
            for score in scores
            if self._thresholds.low < score.confidence < self._thresholds.high
        ]
        outcome = (
            ClassificationOutcome.CATEGORIZED
            if assigned
            else ClassificationOutcome.UNCLEAR
        )
        words = _word_count(message)
        metadata: dict[str, object] = {
            "threshold_profile": self._thresholds.profile_version,
            "low_threshold": self._thresholds.low,
            "high_threshold": self._thresholds.high,
            "aggregation": "max",
            "word_count": words,
            "long_message_word_threshold": self._thresholds.long_message_words,
            "would_escalate_due_to_length": words > self._thresholds.long_message_words,
            "uncertain_categories": sorted(uncertain),
            "raw_similarity": raw_scores,
        }
        if persisted is None:
            metadata["prototype_source"] = "JSON_SEED"
            metadata["prototype_version"] = self._thresholds.profile_version
            metadata["examples_per_category"] = {
                category.value: len(examples)
                for category, examples in sorted(
                    self._prototypes.items(), key=lambda item: item[0].value
                )
            }
        else:
            metadata["prototype_source"] = "PERSISTED"
            metadata["prototype_version"] = persisted.version
            metadata["aggregation"] = persisted.aggregation_method.value
            metadata["prototype_metrics"] = dict(persisted.metrics)
            if raw_mean_scores:
                metadata["raw_mean_similarity"] = raw_mean_scores
            if raw_max_example_scores:
                metadata["raw_max_example_similarity"] = raw_max_example_scores
        return EmbeddingClassificationResult(
            classification=UseCategoryClassification(
                outcome=outcome,
                category_scores=scores,
                assigned_categories=assigned,
            ),
            metadata=metadata,
        )

    def _category_confidence(
        self,
        message_vector: list[float],
        prototype_vectors: list[list[float]],
        aggregation: EmbeddingPrototypeAggregation | None,
        raw_mean_scores: dict[str, float],
        raw_max_example_scores: dict[str, float],
        category: UseCategory,
    ) -> float:
        similarities = [
            cosine_similarity(message_vector, prototype_vector)
            for prototype_vector in prototype_vectors
        ]
        if aggregation is not EmbeddingPrototypeAggregation.HYBRID:
            return max(similarities)

        mean_similarity = similarities[0]
        example_similarity = max(similarities[1:]) if len(similarities) > 1 else 0.0
        raw_mean_scores[category.value] = mean_similarity
        raw_max_example_scores[category.value] = example_similarity
        if example_similarity >= self._thresholds.high and (
            mean_similarity >= self._thresholds.low
        ):
            return example_similarity
        return mean_similarity
