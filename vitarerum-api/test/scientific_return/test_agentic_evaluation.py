"""The measurement instrument must itself be measured.

A gate that reads a report is only as trustworthy as the report, so these pin
what each mode does, what "gap closed" counts as, and that a run writes nothing.
"""

from __future__ import annotations

import hashlib

from app.scientific_return.application.agentic_evaluation import (
    evaluate_agentic_cases,
)
from app.scientific_return.application.evaluation import load_evaluation_cases
from app.scientific_return.application.ports import BibliographicRecord
from app.scientific_return.domain.enums import (
    AgentRecommendedAction,
    InvestigationMode,
)
from app.scientific_return.domain.investigation_contracts import (
    AgentPlan,
    ExecutionBudget,
    ProposedAction,
)

from .test_run_investigation import _Reasoner, _Source


class _EvalReasoner(_Reasoner):
    """Plans against whichever object the observation actually offers.

    The fixture derives object ids from the case id, so a fake that hardcodes
    one would be refused by the policy for the right reason and measure nothing.
    """

    async def plan(self, observation, mode):  # type: ignore[no-untyped-def]
        if not isinstance(self._plan, Exception):
            self._plan = AgentPlan(
                objective="Find inventory evidence.",
                action=ProposedAction(
                    AgentRecommendedAction.SEARCH_INVENTORY_VARIANTS,
                    observation.objects[0].object_id,
                ),
                reasoning_summary="No inventory evidence yet.",
            )
        return await super().plan(observation, mode)


_BUDGET = ExecutionBudget(1, 1, 4, 10, 5)
_CASES = tuple(
    case
    for case in load_evaluation_cases()
    if case.case_id in {"trichoniscoides-machadoi-2025", "cynoscion-regalis-2017"}
)


def _matching_record(case_doi: str, inventory: str) -> BibliographicRecord:
    return BibliographicRecord(
        source="EUROPE_PMC",
        source_record_id="PMC-match",
        title="A study",
        authors=("Rita P. Eusébio",),
        publication_date="2025",
        abstract="A survey.",
        url=None,
        doi=case_doi,
        raw_metadata_hash=hashlib.sha256(case_doi.encode()).hexdigest(),
        indexed_text=f"Material examined. {inventory}.",
        indexed_text_source="full_text",
    )


async def _run(mode: InvestigationMode, source: _Source) -> dict[str, object]:
    return await evaluate_agentic_cases(
        (source,),
        _EvalReasoner(),
        mode=mode,
        budget=_BUDGET,
        allowed_sources=("EUROPE_PMC",),
        cases=_CASES,
    )


async def test_shadow_mode_asks_the_model_and_executes_nothing() -> None:
    source = _Source([])
    report = await _run(InvestigationMode.SHADOW, source)

    assert source.queries == []
    assert report["authorizedCount"] == 0
    assert report["planValidRate"] == 1.0


async def test_policy_only_decides_but_still_executes_nothing() -> None:
    source = _Source([])
    report = await _run(InvestigationMode.POLICY_ONLY, source)

    assert source.queries == []
    # The policy refuses because the mode may not execute, which is the point:
    # POLICY_ONLY measures the decision, not the search.
    assert report["authorizedCount"] == 0
    rejections = report["rejectionsByReason"]
    assert isinstance(rejections, dict)
    assert "MODE_FORBIDS_EXECUTION" in rejections


async def test_supervised_mode_executes_the_authorised_action() -> None:
    source = _Source([])
    report = await _run(InvestigationMode.SUPERVISED, source)

    assert source.queries
    assert report["authorizedCount"] == len(_CASES)


async def test_a_gap_counts_as_closed_only_when_the_case_becomes_actionable() -> None:
    """Retrieval alone is what the old metric counted, and it hid the failure."""
    case = next(
        item for item in _CASES if item.case_id == "trichoniscoides-machadoi-2025"
    )
    source = _Source([_matching_record(case.expected_doi, "MNHNC:MB11:001283")])

    report = await _run(InvestigationMode.SUPERVISED, source)
    closed = report["gapsClosedCaseIds"]

    assert isinstance(closed, list)
    assert "trichoniscoides-machadoi-2025" in closed


async def test_a_retrieved_but_unmatched_record_does_not_close_the_gap() -> None:
    case = next(
        item for item in _CASES if item.case_id == "trichoniscoides-machadoi-2025"
    )
    # Same publication, but the text carries no inventory number.
    record = BibliographicRecord(
        source="EUROPE_PMC",
        source_record_id="PMC-bare",
        title="A study",
        authors=("Someone Else",),
        publication_date="2025",
        abstract="Nothing relevant.",
        url=None,
        doi=case.expected_doi,
        raw_metadata_hash="h",
    )
    report = await _run(InvestigationMode.SUPERVISED, _Source([record]))

    assert report["gapsClosed"] == 0
    cases = report["cases"]
    assert isinstance(cases, list)
    target = next(
        item for item in cases if item["case_id"] == "trichoniscoides-machadoi-2025"
    )
    assert target["target_retrieved"] is True
    assert target["target_actionable"] is False


async def test_the_report_records_what_it_was_run_with() -> None:
    report = await _run(InvestigationMode.SUPERVISED, _Source([]))

    assert report["fixtureVersion"]
    assert report["contractVersion"]
    assert report["mode"] == "SUPERVISED"
    assert report["allowedSources"] == ["EUROPE_PMC"]
    assert report["caseCount"] == len(_CASES)


async def test_the_cycle_starts_from_what_the_pipeline_already_tried() -> None:
    """Otherwise the evaluation would credit the agent with the baseline's work."""
    source = _Source([])
    await _run(InvestigationMode.SUPERVISED, source)

    for query in source.queries:
        assert '"MUHNAC/MB11-001283"' != query
        assert '"MUHNAC/MB06-005747"' != query


async def test_an_invalid_plan_is_counted_not_fatal() -> None:
    from app.scientific_return.application.agent_contracts import AgentPlanSchemaError

    report = await evaluate_agentic_cases(
        (_Source([]),),
        _EvalReasoner(plan=AgentPlanSchemaError("bad json")),
        mode=InvestigationMode.SUPERVISED,
        budget=_BUDGET,
        allowed_sources=("EUROPE_PMC",),
        cases=_CASES,
    )

    assert report["planValidRate"] == 0.0
    assert report["caseCount"] == len(_CASES)
    assert report["authorizedCount"] == 0


async def test_an_unavailable_reflection_is_counted_not_fatal() -> None:
    report = await evaluate_agentic_cases(
        (_Source([]),),
        _EvalReasoner(reflection=TimeoutError("model down")),
        mode=InvestigationMode.SUPERVISED,
        budget=_BUDGET,
        allowed_sources=("EUROPE_PMC",),
        cases=_CASES,
    )

    assert report["reflectionValidRate"] == 0.0
    assert report["planValidRate"] == 1.0
    cases = report["cases"]
    assert isinstance(cases, list)
    assert all(item["reflection_error"] for item in cases)


async def test_the_plan_action_is_reported_for_auditing() -> None:
    report = await _run(InvestigationMode.SUPERVISED, _Source([]))
    cases = report["cases"]

    assert isinstance(cases, list)
    assert all(
        item["plan_action"] == AgentRecommendedAction.SEARCH_INVENTORY_VARIANTS.value
        for item in cases
    )
