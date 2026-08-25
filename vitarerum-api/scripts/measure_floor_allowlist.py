"""Measure the deterministic floor of the autonomous search, per allowlist.

The floor is the part of the flow the source allowlist actually reroutes, and
the part that runs even when the planner's contract fails. It uses no language
model, so this measurement is reproducible: every floor query is sent verbatim
to the live adapter and the result compared against the fixture's expected DOI.

Planner behaviour, semantic reading and queue precision are model-dependent and
are deliberately out of scope here.

    uv run python scripts/measure_floor_allowlist.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.scientific_return.application.evaluation import (  # noqa: E402
    EvaluationCase,
    load_evaluation_fixture,
)
from app.scientific_return.application.full_agentic_strategy import (  # noqa: E402
    deterministic_floor,
    source_result_limit,
)
from app.scientific_return.application.ports import (  # noqa: E402
    BibliographicSource,
)
from app.scientific_return.presentation.dependencies import (  # noqa: E402
    get_bibliographic_sources,
)

# max_queries=12 // 2 and max_results=40, as the executor applies in production.
FLOOR_RESERVATION = 6
BUDGET_MAX_RESULTS = 40
CONFIGURATIONS = {
    "A  CROSSREF,EUROPE_PMC": ("CROSSREF", "EUROPE_PMC"),
    "B  +OPENALEX": ("CROSSREF", "EUROPE_PMC", "OPENALEX"),
    "C  EUROPE_PMC,OPENALEX": ("EUROPE_PMC", "OPENALEX"),
}


@dataclass(frozen=True, slots=True)
class CaseOutcome:
    retrieved: bool
    records: int
    route: tuple[str, ...]


def _normalized_doi(value: str | None) -> str:
    return (value or "").casefold().removeprefix("https://doi.org/")


async def _measure_case(
    case: EvaluationCase,
    sources: dict[str, BibliographicSource],
    allowlist: tuple[str, ...],
) -> tuple[CaseOutcome, int, int]:
    capabilities = tuple(sources[name].capabilities for name in allowlist)
    searches = deterministic_floor(case.snapshot(), capabilities, FLOOR_RESERVATION)
    retrieved = False
    records_read = 0
    queries = 0
    errors = 0
    route: list[str] = []
    for search in searches:
        try:
            records = await sources[search.source].search(
                search.query,
                source_result_limit(
                    sources[search.source].capabilities, BUDGET_MAX_RESULTS
                ),
                author=search.author,
            )
        except Exception as exc:  # pragma: no cover - live network guard
            errors += 1
            route.append(f"{search.source}/{search.strategy.value}=ERROR {exc!r}")
            continue
        queries += 1
        records_read += len(records)
        match = any(
            _normalized_doi(record.doi) == _normalized_doi(case.expected_doi)
            for record in records
        )
        retrieved = retrieved or match
        route.append(
            f"{search.source}/{search.strategy.value}={len(records)}"
            f"{' MATCH' if match else ''}"
        )
    return CaseOutcome(retrieved, records_read, tuple(route)), queries, errors


async def main() -> None:
    fixture = load_evaluation_fixture()
    sources = {source.name: source for source in get_bibliographic_sources()}
    missing = {
        name
        for allowlist in CONFIGURATIONS.values()
        for name in allowlist
        if name not in sources
    }
    if missing:
        raise SystemExit(f"Adapters are not configured: {sorted(missing)}")

    report: dict[str, dict[str, object]] = {}
    for label, allowlist in CONFIGURATIONS.items():
        outcomes: dict[str, CaseOutcome] = {}
        queries = errors = 0
        for case in fixture.cases:
            outcome, case_queries, case_errors = await _measure_case(
                case, sources, allowlist
            )
            outcomes[case.case_id] = outcome
            queries += case_queries
            errors += case_errors
        retrieved = sum(1 for item in outcomes.values() if item.retrieved)
        report[label] = {
            "allowlist": list(allowlist),
            "floorRecall": retrieved / len(outcomes),
            "retrieved": retrieved,
            "caseCount": len(outcomes),
            "queries": queries,
            "recordsRead": sum(item.records for item in outcomes.values()),
            "errors": errors,
            "cases": {
                case_id: {
                    "retrieved": item.retrieved,
                    "records": item.records,
                    "route": list(item.route),
                }
                for case_id, item in outcomes.items()
            },
        }

    labels = list(CONFIGURATIONS)
    mark = {True: "yes", False: "-"}
    header = "  ".join(label.split()[0] for label in labels)
    print(f"{'case':32} {header}  route in the last configuration")
    for case in fixture.cases:
        cells = [
            mark[report[label]["cases"][case.case_id]["retrieved"]]  # type: ignore[index]
            for label in labels
        ]
        last = report[labels[-1]]["cases"][case.case_id]  # type: ignore[index]
        row = "  ".join(f"{cell:>3}" for cell in cells)
        print(f"{case.case_id:32} {row}  {' + '.join(last['route'])}")
    print()
    for label in labels:
        row = report[label]
        print(
            f"{label:26} floorRecall={row['retrieved']}/{row['caseCount']} "
            f"({row['floorRecall']:.1%})  queries={row['queries']}  "
            f"recordsRead={row['recordsRead']}  errors={row['errors']}"
        )
    print()
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
