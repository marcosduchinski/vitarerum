from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import cast

from app.scientific_return.application.analysis import (
    build_evidences,
    deduplication_key,
    is_actionable,
    plan_adaptive_queries,
    plan_queries,
)
from app.scientific_return.application.ports import (
    BibliographicRecord,
    BibliographicSource,
)
from app.scientific_return.domain.models import (
    CandidatePublicationId,
    ConsultedObjectSnapshot,
    ProjectSnapshotPayload,
)


@dataclass(frozen=True, slots=True)
class EvaluationCase:
    case_id: str
    author: str
    inventory_number: str
    object_name: str
    expected_title: str
    expected_doi: str
    notes: str

    def snapshot(self) -> ProjectSnapshotPayload:
        return ProjectSnapshotPayload(
            project_id=f"evaluation-{self.case_id}",
            project_reference=self.case_id,
            researcher=self.author,
            consulted_objects=(
                ConsultedObjectSnapshot(
                    id=f"object-{self.case_id}",
                    inventory_number=self.inventory_number,
                    object_name=self.object_name,
                ),
            ),
        )


@dataclass(frozen=True, slots=True)
class EvaluationTrajectory:
    source: str
    query_type: str
    query: str
    result_count: int
    actionable_count: int
    expected_rank: int | None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class EvaluationEvidence:
    type: str
    strength: str
    value: str
    source_field: str
    explanation: str


@dataclass(frozen=True, slots=True)
class EvaluationCandidate:
    review_id: str
    case_id: str
    deduplication_key: str
    sources: tuple[str, ...]
    source_record_ids: tuple[str, ...]
    doi: str | None
    title: str
    authors: tuple[str, ...]
    publication_date: str | None
    url: str | None
    known_case_match: bool
    evidences: tuple[EvaluationEvidence, ...]
    human_decision: str | None = None
    human_justification: str | None = None
    reviewer: str | None = None
    reviewed_at: str | None = None


@dataclass(frozen=True, slots=True)
class PhaseZeroHumanReview:
    review_id: str
    decision: str
    justification: str
    reviewer: str
    reviewed_at: str


@dataclass(frozen=True, slots=True)
class EvaluationSourceCaseResult:
    source: str
    retrieved: bool
    best_rank: int | None
    actionable_candidates: int
    known_actionable_matches: int
    query_count: int
    error_count: int


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    case_id: str
    expected_doi: str
    retrieved: bool
    best_rank: int | None
    actionable_candidates: int
    trajectories: tuple[EvaluationTrajectory, ...]
    source_results: tuple[EvaluationSourceCaseResult, ...]
    candidates: tuple[EvaluationCandidate, ...]


@dataclass(frozen=True, slots=True)
class EvaluationSourceMetrics:
    source: str
    case_count: int
    retrieved_count: int
    recall: float
    actionable_candidates: int
    known_actionable_matches: int
    known_case_precision_proxy: float
    query_count: int
    error_count: int


@dataclass(frozen=True, slots=True)
class HumanReviewMetrics:
    total_candidates: int
    reviewed_candidates: int
    pending_candidates: int
    confirmed_candidates: int
    dismissed_candidates: int
    uncertain_candidates: int
    review_coverage: float
    human_precision: float | None


@dataclass(slots=True)
class _CandidateAccumulator:
    record: BibliographicRecord
    sources: set[str]
    source_record_ids: set[str]
    evidences: dict[tuple[str, str, str, str, str], EvaluationEvidence]


PHASE_ZERO_CASES = (
    EvaluationCase(
        case_id="rhoptropus-2025",
        author="Diogo Parrinha",
        inventory_number="MUHNAC/MB03-1707",
        object_name="Rhoptropus nivimontanus",
        expected_title="A new species of Namib day gecko from Serra da Neve",
        expected_doi="10.11646/zootaxa.5569.3.2",
        notes="Tests a taxonomic article with public metadata and restricted PDF.",
    ),
    EvaluationCase(
        case_id="acontias-2023",
        author="Mariana P. Marques",
        inventory_number="MUHNAC/MB03-001522",
        object_name="Acontias mukwando",
        expected_title="A new species of African legless skink, genus Acontias",
        expected_doi="10.1080/21564574.2023.2246487",
        notes="Tests MUHNAC/MUNHAC and repeated inventory-code variants.",
    ),
    EvaluationCase(
        case_id="pachydactylus-2025",
        author="Diogo Parrinha",
        inventory_number="MUHNAC/MB03-001801",
        object_name="Pachydactylus namibensis",
        expected_title="Two new species of Pachydactylus from the Kaokoveld",
        expected_doi="10.1643/h2024108",
        notes="Tests metadata coverage for a partially restricted article.",
    ),
    EvaluationCase(
        case_id="serra-da-neve-checklist-2024",
        author="Mariana P. Marques",
        inventory_number="MUNHAC/MB03-001552",
        object_name="Afroedura praedicta",
        expected_title="An island in a sea of sand",
        expected_doi="10.3897/zookeys.1201.120750",
        notes="Tests specimen evidence in the full text of a broad checklist.",
    ),
    EvaluationCase(
        case_id="sao-tome-barcode-2023",
        author="Luis M. P. Ceríaco",
        inventory_number="MUHNAC/MB04-000792",
        object_name="Leptopelis palmatus",
        expected_title="Illustrated keys and a DNA barcode reference library",
        expected_doi="10.3897/zookeys.1168.101334",
        notes="Tests specimen evidence located in an extensive full-text table.",
    ),
)


def _doi(value: str | None) -> str:
    return (value or "").casefold().removeprefix("https://doi.org/")


async def evaluate_cases(
    sources: tuple[BibliographicSource, ...],
    cases: tuple[EvaluationCase, ...] = PHASE_ZERO_CASES,
    result_limit: int = 20,
    human_reviews: dict[str, PhaseZeroHumanReview] | None = None,
) -> dict[str, object]:
    reviews = human_reviews or {}
    results: list[EvaluationResult] = []
    for case in cases:
        snapshot = case.snapshot()
        trajectories: list[EvaluationTrajectory] = []
        candidate_accumulators: dict[str, _CandidateAccumulator] = {}
        source_results: list[EvaluationSourceCaseResult] = []
        best_rank: int | None = None
        for source in sources:
            source_actionable_keys: set[str] = set()
            source_known_actionable_keys: set[str] = set()
            source_best_rank: int | None = None
            source_query_count = 0
            source_error_count = 0
            queries = list(plan_queries(snapshot))
            initial_query_count = len(queries)
            for index, planned in enumerate(queries):
                source_query_count += 1
                try:
                    records = await source.search(planned.text, result_limit)
                except Exception as exc:
                    source_error_count += 1
                    trajectories.append(
                        EvaluationTrajectory(
                            source=source.name,
                            query_type=planned.query_type,
                            query=planned.text,
                            result_count=0,
                            actionable_count=0,
                            expected_rank=None,
                            error=f"{type(exc).__name__}: {exc}"[:500],
                        )
                    )
                    continue

                expected_rank = next(
                    (
                        index
                        for index, record in enumerate(records, start=1)
                        if _doi(record.doi) == _doi(case.expected_doi)
                    ),
                    None,
                )
                if expected_rank is not None:
                    source_best_rank = (
                        expected_rank
                        if source_best_rank is None
                        else min(source_best_rank, expected_rank)
                    )
                    best_rank = (
                        expected_rank
                        if best_rank is None
                        else min(best_rank, expected_rank)
                    )
                actionable_count = 0
                for record in records:
                    evidences = build_evidences(
                        CandidatePublicationId("evaluation"),
                        snapshot,
                        record,
                        datetime.now(tz=UTC),
                    )
                    if is_actionable(evidences):
                        actionable_count += 1
                        key = deduplication_key(record)
                        source_actionable_keys.add(key)
                        if _doi(record.doi) == _doi(case.expected_doi):
                            source_known_actionable_keys.add(key)
                        accumulator = candidate_accumulators.get(key)
                        if accumulator is None:
                            accumulator = _CandidateAccumulator(
                                record=record,
                                sources=set(),
                                source_record_ids=set(),
                                evidences={},
                            )
                            candidate_accumulators[key] = accumulator
                        accumulator.sources.add(record.source)
                        accumulator.source_record_ids.add(record.source_record_id)
                        for evidence in evidences:
                            item = EvaluationEvidence(
                                type=evidence.type.value,
                                strength=evidence.strength.value,
                                value=evidence.value,
                                source_field=evidence.source_field,
                                explanation=evidence.explanation,
                            )
                            evidence_key = (
                                str(item.type),
                                str(item.strength),
                                item.value,
                                item.source_field,
                                item.explanation,
                            )
                            accumulator.evidences[evidence_key] = item
                trajectories.append(
                    EvaluationTrajectory(
                        source=source.name,
                        query_type=planned.query_type,
                        query=planned.text,
                        result_count=len(records),
                        actionable_count=actionable_count,
                        expected_rank=expected_rank,
                    )
                )
                if index + 1 == initial_query_count and not source_actionable_keys:
                    queries.extend(plan_adaptive_queries(snapshot))
            source_results.append(
                EvaluationSourceCaseResult(
                    source=source.name,
                    retrieved=source_best_rank is not None,
                    best_rank=source_best_rank,
                    actionable_candidates=len(source_actionable_keys),
                    known_actionable_matches=len(source_known_actionable_keys),
                    query_count=source_query_count,
                    error_count=source_error_count,
                )
            )
        candidates_list: list[EvaluationCandidate] = []
        for key, accumulator in sorted(candidate_accumulators.items()):
            review_id = f"{case.case_id}|{key}"
            review = reviews.get(review_id)
            candidates_list.append(
                EvaluationCandidate(
                    review_id=review_id,
                    case_id=case.case_id,
                    deduplication_key=key,
                    sources=tuple(sorted(accumulator.sources)),
                    source_record_ids=tuple(sorted(accumulator.source_record_ids)),
                    doi=accumulator.record.doi,
                    title=accumulator.record.title,
                    authors=accumulator.record.authors,
                    publication_date=accumulator.record.publication_date,
                    url=accumulator.record.url,
                    known_case_match=_doi(accumulator.record.doi)
                    == _doi(case.expected_doi),
                    evidences=tuple(accumulator.evidences.values()),
                    human_decision=review.decision if review else None,
                    human_justification=review.justification if review else None,
                    reviewer=review.reviewer if review else None,
                    reviewed_at=review.reviewed_at if review else None,
                )
            )
        candidates = tuple(candidates_list)
        results.append(
            EvaluationResult(
                case_id=case.case_id,
                expected_doi=case.expected_doi,
                retrieved=best_rank is not None,
                best_rank=best_rank,
                actionable_candidates=len(candidate_accumulators),
                trajectories=tuple(trajectories),
                source_results=tuple(source_results),
                candidates=candidates,
            )
        )

    retrieved = sum(item.retrieved for item in results)
    actionable = sum(item.actionable_candidates for item in results)
    known_actionable = sum(
        candidate.known_case_match
        for result in results
        for candidate in result.candidates
    )
    source_metrics = tuple(_source_metrics(source.name, results) for source in sources)
    review_metrics = _human_review_metrics(results)
    return {
        "generatedAt": datetime.now(tz=UTC).isoformat(),
        "caseCount": len(results),
        "retrievedCount": retrieved,
        "recall": retrieved / len(results) if results else 0.0,
        "actionableCandidates": actionable,
        "knownActionableMatches": known_actionable,
        "knownCasePrecisionProxy": (
            known_actionable / actionable if actionable else 0.0
        ),
        "sourceMetrics": [asdict(item) for item in source_metrics],
        "humanReviewMetrics": asdict(review_metrics),
        "reviewQueue": [
            asdict(candidate) for result in results for candidate in result.candidates
        ],
        "cases": [asdict(item) for item in results],
    }


def parse_human_reviews(payload: object) -> dict[str, PhaseZeroHumanReview]:
    if not isinstance(payload, dict):
        raise ValueError("The Phase 0 review file must contain a JSON object")
    raw_items = payload.get("reviews", payload.get("reviewQueue"))
    if not isinstance(raw_items, list):
        raise ValueError("The Phase 0 review file needs a reviews or reviewQueue list")

    reviews: dict[str, PhaseZeroHumanReview] = {}
    allowed = {"CONFIRMED", "DISMISSED", "UNCERTAIN"}
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            raise ValueError("Every Phase 0 review must be a JSON object")
        item = cast(dict[str, object], raw_item)
        decision = str(item.get("human_decision") or "").strip().upper()
        if not decision:
            continue
        if decision not in allowed:
            raise ValueError(
                "human_decision must be CONFIRMED, DISMISSED or UNCERTAIN"
            )
        review_id = str(item.get("review_id") or "").strip()
        justification = str(item.get("human_justification") or "").strip()
        reviewer = str(item.get("reviewer") or "").strip()
        reviewed_at = str(item.get("reviewed_at") or "").strip()
        if not all((review_id, justification, reviewer, reviewed_at)):
            raise ValueError(
                "Reviewed candidates require review_id, human_justification, "
                "reviewer and reviewed_at"
            )
        if review_id in reviews:
            raise ValueError(f"Duplicate Phase 0 review_id: {review_id}")
        try:
            reviewed_datetime = datetime.fromisoformat(
                reviewed_at.replace("Z", "+00:00")
            )
        except ValueError:
            raise ValueError("reviewed_at must be an ISO 8601 datetime") from None
        if reviewed_datetime.tzinfo is None:
            raise ValueError("reviewed_at must include a timezone")
        reviews[review_id] = PhaseZeroHumanReview(
            review_id=review_id,
            decision=decision,
            justification=justification,
            reviewer=reviewer,
            reviewed_at=reviewed_at,
        )
    return reviews


def finalize_human_review_report(payload: object) -> dict[str, object]:
    reviews = parse_human_reviews(payload)
    if not isinstance(payload, dict):
        raise ValueError("The Phase 0 review file must contain a JSON object")
    raw_queue = payload.get("reviewQueue")
    if not isinstance(raw_queue, list):
        raise ValueError("The Phase 0 report needs its original reviewQueue")

    decisions = [review.decision for review in reviews.values()]
    confirmed = decisions.count("CONFIRMED")
    dismissed = decisions.count("DISMISSED")
    uncertain = decisions.count("UNCERTAIN")
    decided = confirmed + dismissed
    metrics = HumanReviewMetrics(
        total_candidates=len(raw_queue),
        reviewed_candidates=len(decisions),
        pending_candidates=len(raw_queue) - len(decisions),
        confirmed_candidates=confirmed,
        dismissed_candidates=dismissed,
        uncertain_candidates=uncertain,
        review_coverage=len(decisions) / len(raw_queue) if raw_queue else 0.0,
        human_precision=confirmed / decided if decided else None,
    )
    report = cast(dict[str, object], dict(payload))
    report["humanReviewMetrics"] = asdict(metrics)
    report["reviewFinalizedAt"] = datetime.now(tz=UTC).isoformat()
    return report


def _source_metrics(
    source: str, results: list[EvaluationResult]
) -> EvaluationSourceMetrics:
    source_results = [
        item
        for result in results
        for item in result.source_results
        if item.source == source
    ]
    retrieved = sum(item.retrieved for item in source_results)
    actionable = sum(item.actionable_candidates for item in source_results)
    known_actionable = sum(item.known_actionable_matches for item in source_results)
    return EvaluationSourceMetrics(
        source=source,
        case_count=len(source_results),
        retrieved_count=retrieved,
        recall=retrieved / len(source_results) if source_results else 0.0,
        actionable_candidates=actionable,
        known_actionable_matches=known_actionable,
        known_case_precision_proxy=(
            known_actionable / actionable if actionable else 0.0
        ),
        query_count=sum(item.query_count for item in source_results),
        error_count=sum(item.error_count for item in source_results),
    )


def _human_review_metrics(results: list[EvaluationResult]) -> HumanReviewMetrics:
    candidates = [candidate for result in results for candidate in result.candidates]
    decisions = [
        candidate.human_decision
        for candidate in candidates
        if candidate.human_decision is not None
    ]
    confirmed = decisions.count("CONFIRMED")
    dismissed = decisions.count("DISMISSED")
    uncertain = decisions.count("UNCERTAIN")
    decided = confirmed + dismissed
    return HumanReviewMetrics(
        total_candidates=len(candidates),
        reviewed_candidates=len(decisions),
        pending_candidates=len(candidates) - len(decisions),
        confirmed_candidates=confirmed,
        dismissed_candidates=dismissed,
        uncertain_candidates=uncertain,
        review_coverage=len(decisions) / len(candidates) if candidates else 0.0,
        human_precision=confirmed / decided if decided else None,
    )
