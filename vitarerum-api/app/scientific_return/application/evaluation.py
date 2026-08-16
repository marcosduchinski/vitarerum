from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from app.scientific_return.application.analysis import (
    build_evidences,
    deduplication_key,
    is_actionable,
    plan_adaptive_queries,
    plan_queries,
)
from app.scientific_return.application.ports import BibliographicSource
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
class EvaluationResult:
    case_id: str
    expected_doi: str
    retrieved: bool
    best_rank: int | None
    actionable_candidates: int
    trajectories: tuple[EvaluationTrajectory, ...]


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
) -> dict[str, object]:
    results: list[EvaluationResult] = []
    for case in cases:
        snapshot = case.snapshot()
        trajectories: list[EvaluationTrajectory] = []
        actionable_keys: set[str] = set()
        best_rank: int | None = None
        for source in sources:
            source_actionable_count = 0
            queries = list(plan_queries(snapshot))
            initial_query_count = len(queries)
            for index, planned in enumerate(queries):
                try:
                    records = await source.search(planned.text, result_limit)
                except Exception as exc:
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
                        source_actionable_count += 1
                        actionable_keys.add(deduplication_key(record))
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
                if index + 1 == initial_query_count and not source_actionable_count:
                    queries.extend(plan_adaptive_queries(snapshot))
        results.append(
            EvaluationResult(
                case_id=case.case_id,
                expected_doi=case.expected_doi,
                retrieved=best_rank is not None,
                best_rank=best_rank,
                actionable_candidates=len(actionable_keys),
                trajectories=tuple(trajectories),
            )
        )

    retrieved = sum(item.retrieved for item in results)
    actionable = sum(item.actionable_candidates for item in results)
    return {
        "generatedAt": datetime.now(tz=UTC).isoformat(),
        "caseCount": len(results),
        "retrievedCount": retrieved,
        "recall": retrieved / len(results) if results else 0.0,
        "actionableCandidates": actionable,
        "knownCasePrecisionProxy": retrieved / actionable if actionable else 0.0,
        "cases": [asdict(item) for item in results],
    }
