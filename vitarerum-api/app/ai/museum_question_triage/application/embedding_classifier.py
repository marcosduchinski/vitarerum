from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

from app.ai.museum_question_triage.domain.models import (
    ClassificationOutcome,
    ClassificationScoreSource,
    UseCategory,
    UseCategoryClassification,
    UseCategoryScore,
)
from app.ai.museum_question_triage.domain.ports import EmbeddingClassifierPort

_PROTOTYPES_PATH = Path(__file__).with_name("use_category_prototypes.json")


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
    ) -> None:
        self._embedding = embedding
        self._thresholds = thresholds
        self._prototypes = prototypes or load_use_category_prototypes()

    async def classify(self, message: str) -> EmbeddingClassificationResult:
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
        scores: list[UseCategoryScore] = []
        raw_scores: dict[str, float] = {}
        vectors_by_category: dict[UseCategory, list[list[float]]] = {
            category: [] for category in self._prototypes
        }
        for (category, _prototype), prototype_vector in zip(
            prototype_items, prototype_vectors, strict=True
        ):
            vectors_by_category[category].append(prototype_vector)

        for category in sorted(self._prototypes, key=lambda item: item.value):
            similarities = [
                cosine_similarity(message_vector, prototype_vector)
                for prototype_vector in vectors_by_category[category]
            ]
            confidence = max(similarities)
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
        return EmbeddingClassificationResult(
            classification=UseCategoryClassification(
                outcome=outcome,
                category_scores=scores,
                assigned_categories=assigned,
            ),
            metadata=metadata,
        )
