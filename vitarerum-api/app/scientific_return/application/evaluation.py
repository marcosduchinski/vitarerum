from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, cast

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
from app.scientific_return.domain.enums import EvidenceType
from app.scientific_return.domain.models import (
    CandidatePublicationId,
    ConsultedObjectSnapshot,
    ProjectSnapshotPayload,
)


class BaselineStatus(StrEnum):
    """Whether the deterministic baseline puts the expected publication in the queue.

    ``RESOLVED`` is deliberately stricter than "the DOI appeared in some result
    list": a publication that is retrieved but fails the actionable-evidence
    gate never reaches a human, so for the purposes of scientific return it was
    not found at all.
    """

    RESOLVED = "RESOLVED"
    GAP = "GAP"
    UNVERIFIED = "UNVERIFIED"


class ExpectedGap(StrEnum):
    """Why a case is expected to defeat the deterministic baseline.

    The kind matters for promotion gates: an ``INVENTORY_FORMAT`` gap is one the
    inventory-variant generator is meant to close, while the others need
    capabilities that are not part of the first agentic increment.
    """

    NONE = "NONE"
    UNKNOWN = "UNKNOWN"
    INVENTORY_FORMAT = "INVENTORY_FORMAT"
    INSTITUTIONAL_ACRONYM = "INSTITUTIONAL_ACRONYM"
    NO_INVENTORY_IN_TEXT = "NO_INVENTORY_IN_TEXT"
    NOT_INDEXED = "NOT_INDEXED"


class AgenticObjective(StrEnum):
    """Which agentic objective a case is a target for.

    Derived from the measured baseline rather than declared, so it cannot go
    stale: a case the baseline never turns into a reviewable candidate is a
    discovery target, and one that reaches the queue without inventory evidence
    is an enrichment target.
    """

    NONE = "NONE"
    DISCOVER_CANDIDATE = "DISCOVER_CANDIDATE"
    ENRICH_CANDIDATE = "ENRICH_CANDIDATE"


_INVENTORY_EVIDENCE_TYPES = frozenset(
    {
        str(EvidenceType.INVENTORY_NUMBER),
        str(EvidenceType.AUTHOR_INVENTORY),
        str(EvidenceType.INVENTORY_OBJECT),
    }
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
    baseline_status: BaselineStatus = BaselineStatus.UNVERIFIED
    baseline_inventory_evidence: bool | None = None
    expected_gap: ExpectedGap = ExpectedGap.NONE
    cited_inventory_forms: tuple[str, ...] = field(default_factory=tuple)

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
    declared_baseline_status: str = BaselineStatus.UNVERIFIED
    observed_baseline_status: str = BaselineStatus.UNVERIFIED
    observed_inventory_evidence: bool = False
    agentic_objective: str = AgenticObjective.NONE
    expected_gap: str = ExpectedGap.NONE
    declaration_matches: bool = True


@dataclass(frozen=True, slots=True)
class BaselineDeclarationMetrics:
    """How the fixture's declarations compare with this run.

    A fixture whose declarations drift from reality is worse than no fixture,
    because the promotion gates read the declarations. Mismatches are reported
    per case so the fixture can be corrected before a gate is evaluated.
    """

    declared_resolved: int
    declared_gap: int
    declared_unverified: int
    observed_resolved: int
    observed_gap: int
    mismatched_case_ids: tuple[str, ...]
    unverified_case_ids: tuple[str, ...]
    discovery_target_case_ids: tuple[str, ...]
    enrichment_target_case_ids: tuple[str, ...]
    inventory_format_gap_case_ids: tuple[str, ...]


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


_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "evaluation_cases.json"


@dataclass(frozen=True, slots=True)
class UnmappedPaper:
    """A MUHNAC publication that is not yet expressible as a case.

    Keeping these visible stops the fixture from silently pretending the corpus
    is fully covered: each entry names the collection series whose museum-side
    inventory number is still unknown.
    """

    reference: str
    expected_doi: str
    cited_inventory_forms: tuple[str, ...]
    reason: str


@dataclass(frozen=True, slots=True)
class EvaluationFixture:
    version: str
    cases: tuple[EvaluationCase, ...]
    unmapped_papers: tuple[UnmappedPaper, ...]


def _required_text(payload: dict[str, Any], key: str, where: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{where}: '{key}' must be a non-empty string")
    return value.strip()


def _text_tuple(payload: dict[str, Any], key: str, where: str) -> tuple[str, ...]:
    value = payload.get(key, [])
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{where}: '{key}' must be an array of strings")
    return tuple(item.strip() for item in value if item.strip())


def _case_from_payload(payload: dict[str, Any]) -> EvaluationCase:
    case_id = _required_text(payload, "caseId", "case")
    where = f"case {case_id}"
    try:
        baseline_status = BaselineStatus(
            _required_text(payload, "baselineStatus", where)
        )
        expected_gap = ExpectedGap(_required_text(payload, "expectedGap", where))
    except ValueError as exc:
        raise ValueError(f"{where}: unsupported enum value: {exc}") from exc
    inventory_evidence = payload.get("baselineInventoryEvidence")
    if inventory_evidence is not None and not isinstance(inventory_evidence, bool):
        raise ValueError(f"{where}: 'baselineInventoryEvidence' must be a boolean")
    if baseline_status is BaselineStatus.UNVERIFIED and inventory_evidence is not None:
        raise ValueError(
            f"{where}: an UNVERIFIED case cannot declare baselineInventoryEvidence"
        )
    if (
        baseline_status is BaselineStatus.RESOLVED
        and inventory_evidence is True
        and expected_gap is not ExpectedGap.NONE
    ):
        raise ValueError(
            f"{where}: a case the baseline fully resolves, inventory evidence "
            "included, cannot also declare a gap"
        )
    if baseline_status is BaselineStatus.GAP and expected_gap is ExpectedGap.NONE:
        raise ValueError(f"{where}: a GAP case must declare why it is a gap")
    return EvaluationCase(
        case_id=case_id,
        author=_required_text(payload, "author", where),
        inventory_number=_required_text(payload, "inventoryNumber", where),
        object_name=_required_text(payload, "objectName", where),
        expected_title=_required_text(payload, "expectedTitle", where),
        expected_doi=_required_text(payload, "expectedDoi", where),
        notes=_required_text(payload, "notes", where),
        baseline_status=baseline_status,
        baseline_inventory_evidence=inventory_evidence,
        expected_gap=expected_gap,
        cited_inventory_forms=_text_tuple(payload, "citedInventoryForms", where),
    )


def load_evaluation_fixture(path: Path | None = None) -> EvaluationFixture:
    """Read the versioned evaluation fixture from disk.

    The cases used to live in this module as a literal tuple, which made them
    impossible to version independently of the code that consumes them.
    """
    source = path or _FIXTURE_PATH
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("The evaluation fixture must be a JSON object")
    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError("The evaluation fixture must declare at least one case")
    cases = tuple(
        _case_from_payload(cast(dict[str, Any], item))
        for item in raw_cases
        if isinstance(item, dict)
    )
    identifiers = [case.case_id for case in cases]
    duplicates = sorted({item for item in identifiers if identifiers.count(item) > 1})
    if duplicates:
        raise ValueError(f"Duplicated case ids in the fixture: {duplicates}")
    raw_unmapped = payload.get("unmappedPapers", [])
    if not isinstance(raw_unmapped, list):
        raise ValueError("'unmappedPapers' must be an array")
    unmapped = tuple(
        UnmappedPaper(
            reference=_required_text(item, "reference", "unmapped paper"),
            expected_doi=_required_text(item, "expectedDoi", "unmapped paper"),
            cited_inventory_forms=_text_tuple(
                item, "citedInventoryForms", "unmapped paper"
            ),
            reason=_required_text(item, "reason", "unmapped paper"),
        )
        for item in raw_unmapped
        if isinstance(item, dict)
    )
    return EvaluationFixture(
        version=_required_text(payload, "version", "fixture"),
        cases=cases,
        unmapped_papers=unmapped,
    )


def load_evaluation_cases(path: Path | None = None) -> tuple[EvaluationCase, ...]:
    return load_evaluation_fixture(path).cases


def _doi(value: str | None) -> str:
    return (value or "").casefold().removeprefix("https://doi.org/")


async def evaluate_cases(
    sources: tuple[BibliographicSource, ...],
    cases: tuple[EvaluationCase, ...] | None = None,
    result_limit: int = 20,
    human_reviews: dict[str, PhaseZeroHumanReview] | None = None,
) -> dict[str, object]:
    if cases is None:
        fixture = load_evaluation_fixture()
        cases = fixture.cases
        fixture_version = fixture.version
    else:
        fixture_version = "caller-supplied"
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
                    records = await source.search(
                        planned.text, result_limit, author=planned.author
                    )
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
        known = tuple(item for item in candidates if item.known_case_match)
        inventory_evidence = any(
            evidence.type in _INVENTORY_EVIDENCE_TYPES
            for candidate in known
            for evidence in candidate.evidences
        )
        observed = BaselineStatus.RESOLVED if known else BaselineStatus.GAP
        if not known:
            objective = AgenticObjective.DISCOVER_CANDIDATE
        elif not inventory_evidence:
            objective = AgenticObjective.ENRICH_CANDIDATE
        else:
            objective = AgenticObjective.NONE
        declared_evidence = case.baseline_inventory_evidence
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
                declared_baseline_status=case.baseline_status,
                observed_baseline_status=observed,
                observed_inventory_evidence=inventory_evidence,
                agentic_objective=objective,
                expected_gap=case.expected_gap,
                declaration_matches=(
                    case.baseline_status is BaselineStatus.UNVERIFIED
                    or (
                        case.baseline_status is observed
                        and (
                            declared_evidence is None
                            or declared_evidence == inventory_evidence
                        )
                    )
                ),
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
    declaration_metrics = _baseline_declaration_metrics(cases, results)
    return {
        "generatedAt": datetime.now(tz=UTC).isoformat(),
        "fixtureVersion": fixture_version,
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
        "baselineDeclarationMetrics": asdict(declaration_metrics),
        "reviewQueue": [
            asdict(candidate) for result in results for candidate in result.candidates
        ],
        "cases": [asdict(item) for item in results],
    }


def _baseline_declaration_metrics(
    cases: tuple[EvaluationCase, ...],
    results: list[EvaluationResult],
) -> BaselineDeclarationMetrics:
    by_id = {case.case_id: case for case in cases}
    return BaselineDeclarationMetrics(
        declared_resolved=sum(
            case.baseline_status is BaselineStatus.RESOLVED for case in cases
        ),
        declared_gap=sum(case.baseline_status is BaselineStatus.GAP for case in cases),
        declared_unverified=sum(
            case.baseline_status is BaselineStatus.UNVERIFIED for case in cases
        ),
        observed_resolved=sum(
            result.observed_baseline_status == BaselineStatus.RESOLVED
            for result in results
        ),
        observed_gap=sum(
            result.observed_baseline_status == BaselineStatus.GAP for result in results
        ),
        mismatched_case_ids=tuple(
            result.case_id for result in results if not result.declaration_matches
        ),
        unverified_case_ids=tuple(
            result.case_id
            for result in results
            if result.declared_baseline_status == BaselineStatus.UNVERIFIED
        ),
        discovery_target_case_ids=tuple(
            result.case_id
            for result in results
            if result.agentic_objective == AgenticObjective.DISCOVER_CANDIDATE
        ),
        enrichment_target_case_ids=tuple(
            result.case_id
            for result in results
            if result.agentic_objective == AgenticObjective.ENRICH_CANDIDATE
        ),
        inventory_format_gap_case_ids=tuple(
            result.case_id
            for result in results
            if result.agentic_objective != AgenticObjective.NONE
            and by_id[result.case_id].expected_gap
            in {ExpectedGap.INVENTORY_FORMAT, ExpectedGap.INSTITUTIONAL_ACRONYM}
        ),
    )


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
            raise ValueError("human_decision must be CONFIRMED, DISMISSED or UNCERTAIN")
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
