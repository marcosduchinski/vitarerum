"""Replayable quality metrics for labelled Scientific Return Test runs."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BenchEvaluationObservation:
    expected_relevant: bool
    candidate_ranks: tuple[int, ...]
    grounded_candidates: int = 0
    rejected_claims: int = 0


@dataclass(frozen=True, slots=True)
class BenchEvaluationMetrics:
    precision_at_k: float
    recall_at_k: float
    mean_reciprocal_rank: float
    grounded_evidence_coverage: float
    rejected_claim_rate: float
    zero_result_rate: float


def evaluate_bench(
    observations: tuple[BenchEvaluationObservation, ...], *, k: int = 10
) -> BenchEvaluationMetrics:
    if k < 1:
        raise ValueError("k must be positive")
    if not observations:
        return BenchEvaluationMetrics(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    true_positives = sum(
        observation.expected_relevant
        and any(rank <= k for rank in observation.candidate_ranks)
        for observation in observations
    )
    returned = sum(
        min(k, len(observation.candidate_ranks)) for observation in observations
    )
    expected = sum(observation.expected_relevant for observation in observations)
    reciprocal_ranks = [
        1 / min(observation.candidate_ranks)
        if observation.expected_relevant and observation.candidate_ranks
        else 0.0
        for observation in observations
    ]
    candidates = sum(len(observation.candidate_ranks) for observation in observations)
    grounded = sum(observation.grounded_candidates for observation in observations)
    rejected = sum(observation.rejected_claims for observation in observations)
    claim_total = grounded + rejected
    return BenchEvaluationMetrics(
        precision_at_k=true_positives / returned if returned else 0.0,
        recall_at_k=true_positives / expected if expected else 0.0,
        mean_reciprocal_rank=sum(reciprocal_ranks) / len(observations),
        grounded_evidence_coverage=grounded / candidates if candidates else 0.0,
        rejected_claim_rate=rejected / claim_total if claim_total else 0.0,
        zero_result_rate=sum(not item.candidate_ranks for item in observations)
        / len(observations),
    )
