from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.identity.public import PermissionId
from app.scientific_return.domain.enums import (
    AgentProgress,
    AgentRecommendedAction,
    EvidenceType,
    InvestigationMode,
    InvestigationObjective,
    InvestigationStatus,
    IterationStatus,
    PolicyRejectionReason,
    StopReason,
)
from app.scientific_return.domain.investigation_contracts import (
    AgentObservation,
    AgentPlan,
    AgentReflection,
    EvidenceDelta,
    ExecutionBudget,
    ObservedObject,
    PolicyDecision,
    ProposedAction,
    ToolResultSummary,
)
from app.scientific_return.domain.investigation_models import (
    InvestigationId,
    InvestigationTransitionError,
    ScientificReturnInvestigation,
)
from app.scientific_return.domain.models import (
    CandidatePublicationId,
    ScientificReturnRunId,
    ScientificReturnWatchId,
)

_NOW = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)


def _tick(step: int = 1) -> datetime:
    return _NOW + timedelta(seconds=step)


def _budget(**overrides: int) -> ExecutionBudget:
    values: dict[str, int] = {
        "max_iterations": 1,
        "max_actions": 1,
        "max_queries": 4,
        "max_results_per_query": 10,
        "max_new_candidates": 5,
    }
    values.update(overrides)
    return ExecutionBudget(**values)


def _investigation(**overrides: object) -> ScientificReturnInvestigation:
    values: dict[str, object] = {
        "id": InvestigationId("inv-1"),
        "watch_id": ScientificReturnWatchId("watch-1"),
        "objective": InvestigationObjective.DISCOVER_CANDIDATE,
        "mode": InvestigationMode.SUPERVISED,
        "initial_run_id": ScientificReturnRunId("run-1"),
        "budget": _budget(),
        "created_by": PermissionId("perm-1"),
        "started_at": _NOW,
    }
    values.update(overrides)
    return ScientificReturnInvestigation(**values)  # type: ignore[arg-type]


def _observation() -> AgentObservation:
    return AgentObservation(
        objective=InvestigationObjective.DISCOVER_CANDIDATE,
        project_reference="PRJ-1",
        researcher="Pedro Gomes",
        objects=(ObservedObject("object-1", "MUHNAC/MB06-005747", "Cynoscion"),),
        tried_queries=(),
        allowed_actions=(AgentRecommendedAction.SEARCH_INVENTORY_VARIANTS,),
        budget=_budget(),
    )


def _plan(
    action: AgentRecommendedAction = AgentRecommendedAction.SEARCH_INVENTORY_VARIANTS,
) -> AgentPlan:
    object_id = "object-1" if action.startswith("SEARCH") else None
    return AgentPlan(
        objective="Find inventory evidence.",
        action=ProposedAction(action, object_id),
        reasoning_summary="No inventory evidence yet.",
    )


def _reflection() -> AgentReflection:
    return AgentReflection(
        progress=AgentProgress.EVIDENCE_ADDED,
        evidence_delta_summary="One evidence added.",
        recommended_stop=True,
        reasoning_summary="Objective met.",
    )


def _tool_result(candidates: int = 0) -> ToolResultSummary:
    return ToolResultSummary(
        executed_queries=("MB06-005747",),
        sources=("CROSSREF",),
        total_results=3,
        created_candidate_ids=tuple(f"cand-{i}" for i in range(candidates)),
    )


def _run_to_reflecting(
    investigation: ScientificReturnInvestigation,
) -> ScientificReturnInvestigation:
    investigation.begin_observation(_tick(1))
    investigation.record_observation(_observation(), _tick(2))
    investigation.record_plan(_plan(), _tick(3))
    investigation.record_policy_decision(
        PolicyDecision.authorize("Allowed."), _tick(4), reserved_queries=4
    )
    investigation.record_tool_result(
        _tool_result(), "hash-before", "hash-after", EvidenceDelta(), _tick(5)
    )
    return investigation


# --- happy path --------------------------------------------------------------


def test_the_full_cycle_ends_awaiting_human_review() -> None:
    investigation = _run_to_reflecting(_investigation())
    investigation.record_reflection(_reflection())
    investigation.present_for_review(StopReason.EVIDENCE_SUFFICIENT, _tick(6))

    assert investigation.status is InvestigationStatus.AWAITING_HUMAN_REVIEW
    assert investigation.stop_reason is StopReason.EVIDENCE_SUFFICIENT
    assert investigation.completed_at == _tick(6)
    assert investigation.iterations[0].status is IterationStatus.COMPLETED


def test_a_rejected_action_skips_execution_but_still_reflects() -> None:
    investigation = _investigation()
    investigation.begin_observation(_tick(1))
    investigation.record_observation(_observation(), _tick(2))
    investigation.record_plan(_plan(), _tick(3))
    investigation.record_policy_decision(
        PolicyDecision.reject(
            PolicyRejectionReason.NO_NEW_QUERY_VARIANT, "Every variant was tried."
        ),
        _tick(4),
    )

    assert investigation.status is InvestigationStatus.REFLECTING

    investigation.record_reflection(_reflection())
    investigation.stop(StopReason.QUERY_REPEATED, _tick(5))

    assert investigation.stop_reason is StopReason.QUERY_REPEATED
    decision = investigation.iterations[0].policy_decision
    assert decision is not None and not decision.authorized


def test_every_transition_advances_the_version_and_heartbeat() -> None:
    investigation = _investigation()
    investigation.begin_observation(_tick(1))

    assert investigation.version == 1
    assert investigation.heartbeat_at == _tick(1)

    investigation.record_observation(_observation(), _tick(2))

    assert investigation.version == 2
    assert investigation.heartbeat_at == _tick(2)


# --- forbidden transitions ---------------------------------------------------


def test_planning_cannot_be_skipped() -> None:
    investigation = _investigation()
    investigation.begin_observation(_tick(1))

    with pytest.raises(InvestigationTransitionError, match="Cannot move"):
        investigation.record_plan(_plan(), _tick(2))


def test_execution_cannot_be_reached_without_a_policy_decision() -> None:
    investigation = _investigation()
    investigation.begin_observation(_tick(1))
    investigation.record_observation(_observation(), _tick(2))
    investigation.record_plan(_plan(), _tick(3))

    with pytest.raises(InvestigationTransitionError, match="not authorized"):
        investigation.record_tool_result(
            _tool_result(), "a", "b", EvidenceDelta(), _tick(4)
        )


def test_a_rejected_action_cannot_then_record_a_tool_result() -> None:
    """A refusal must not be followed by an execution it never authorised."""
    investigation = _investigation()
    investigation.begin_observation(_tick(1))
    investigation.record_observation(_observation(), _tick(2))
    investigation.record_plan(_plan(), _tick(3))
    investigation.record_policy_decision(
        PolicyDecision.reject(
            PolicyRejectionReason.ACTION_NOT_ALLOWED, "Not enabled."
        ),
        _tick(4),
    )

    with pytest.raises(InvestigationTransitionError, match="not authorized"):
        investigation.record_tool_result(
            _tool_result(), "a", "b", EvidenceDelta(), _tick(5)
        )


def test_a_terminal_investigation_cannot_run_a_tool() -> None:
    investigation = _run_to_reflecting(_investigation())
    investigation.record_reflection(_reflection())
    investigation.stop(StopReason.NO_RESULTS, _tick(6))

    with pytest.raises(InvestigationTransitionError, match="cannot move"):
        investigation.begin_observation(_tick(7))


def test_a_terminal_investigation_cannot_be_closed_again() -> None:
    investigation = _run_to_reflecting(_investigation())
    investigation.record_reflection(_reflection())
    investigation.present_for_review(StopReason.EVIDENCE_SUFFICIENT, _tick(6))

    with pytest.raises(InvestigationTransitionError):
        investigation.stop(StopReason.NO_RESULTS, _tick(7))


def test_a_terminal_investigation_cannot_fail() -> None:
    investigation = _run_to_reflecting(_investigation())
    investigation.record_reflection(_reflection())
    investigation.stop(StopReason.NO_RESULTS, _tick(6))

    with pytest.raises(InvestigationTransitionError, match="already ended"):
        investigation.fail(StopReason.TOOL_FAILED, "late", _tick(7))


def test_closing_requires_reflecting() -> None:
    investigation = _investigation()
    investigation.begin_observation(_tick(1))

    with pytest.raises(InvestigationTransitionError, match="only close from"):
        investigation.stop(StopReason.NO_RESULTS, _tick(2))


def test_a_reflection_cannot_be_recorded_before_reflecting() -> None:
    investigation = _investigation()
    investigation.begin_observation(_tick(1))
    investigation.record_observation(_observation(), _tick(2))

    with pytest.raises(InvestigationTransitionError, match="while reflecting"):
        investigation.record_reflection(_reflection())


# --- failure -----------------------------------------------------------------


def test_failure_is_reachable_from_any_live_state() -> None:
    investigation = _investigation()
    investigation.begin_observation(_tick(1))
    investigation.fail(StopReason.REASONER_UNAVAILABLE, "Ollama timed out", _tick(2))

    assert investigation.status is InvestigationStatus.FAILED
    assert investigation.stop_reason is StopReason.REASONER_UNAVAILABLE
    assert investigation.iterations[0].status is IterationStatus.FAILED
    assert investigation.iterations[0].error_message == "Ollama timed out"


def test_a_tool_failure_still_reaches_reflection() -> None:
    investigation = _investigation()
    investigation.begin_observation(_tick(1))
    investigation.record_observation(_observation(), _tick(2))
    investigation.record_plan(_plan(), _tick(3))
    investigation.record_policy_decision(
        PolicyDecision.authorize("Allowed."), _tick(4), reserved_queries=4
    )
    investigation.record_tool_failure("Crossref returned 503", _tick(5))

    assert investigation.status is InvestigationStatus.REFLECTING

    investigation.record_reflection(
        AgentReflection.deterministic_fallback(EvidenceDelta())
    )
    investigation.stop(StopReason.TOOL_UNAVAILABLE, _tick(6))

    assert investigation.stop_reason is StopReason.TOOL_UNAVAILABLE


# --- budget ------------------------------------------------------------------


def test_the_budget_is_charged_before_the_tool_runs() -> None:
    investigation = _investigation()
    investigation.begin_observation(_tick(1))
    investigation.record_observation(_observation(), _tick(2))
    investigation.record_plan(_plan(), _tick(3))
    investigation.record_policy_decision(
        PolicyDecision.authorize("Allowed."), _tick(4), reserved_queries=3
    )

    assert investigation.budget.remaining_queries == 1
    assert investigation.budget.remaining_actions == 0


def test_an_authorized_search_must_reserve_queries() -> None:
    investigation = _investigation()
    investigation.begin_observation(_tick(1))
    investigation.record_observation(_observation(), _tick(2))
    investigation.record_plan(_plan(), _tick(3))

    with pytest.raises(ValueError, match="must reserve queries"):
        investigation.record_policy_decision(
            PolicyDecision.authorize("Allowed."), _tick(4)
        )


def test_a_terminating_action_reserves_no_queries() -> None:
    investigation = _investigation()
    investigation.begin_observation(_tick(1))
    investigation.record_observation(_observation(), _tick(2))
    investigation.record_plan(
        _plan(AgentRecommendedAction.PRESENT_FOR_REVIEW), _tick(3)
    )
    investigation.record_policy_decision(
        PolicyDecision.authorize("Nothing to execute."), _tick(4)
    )

    assert investigation.budget.remaining_queries == 4


def test_a_second_iteration_is_refused_once_the_limit_is_reached() -> None:
    investigation = _run_to_reflecting(_investigation())
    investigation.record_reflection(_reflection())

    with pytest.raises(InvestigationTransitionError, match="budget is exhausted"):
        investigation.begin_observation(_tick(6))


def test_created_candidates_are_charged_to_the_budget() -> None:
    investigation = _investigation(budget=_budget(max_new_candidates=2))
    investigation.begin_observation(_tick(1))
    investigation.record_observation(_observation(), _tick(2))
    investigation.record_plan(_plan(), _tick(3))
    investigation.record_policy_decision(
        PolicyDecision.authorize("Allowed."), _tick(4), reserved_queries=4
    )
    investigation.record_tool_result(
        _tool_result(candidates=2), "a", "b", EvidenceDelta(), _tick(5)
    )

    assert investigation.budget.remaining_candidates == 0
    assert investigation.budget.exhaustion() is StopReason.ITERATION_LIMIT_REACHED


# --- construction invariants -------------------------------------------------


def test_enrichment_requires_a_candidate() -> None:
    with pytest.raises(ValueError, match="Enrichment requires a candidate"):
        _investigation(objective=InvestigationObjective.ENRICH_CANDIDATE)


def test_discovery_refuses_a_candidate() -> None:
    with pytest.raises(ValueError, match="starts without a candidate"):
        _investigation(candidate_id=CandidatePublicationId("cand-1"))


def test_an_enrichment_investigation_is_valid_with_its_candidate() -> None:
    investigation = _investigation(
        objective=InvestigationObjective.ENRICH_CANDIDATE,
        candidate_id=CandidatePublicationId("cand-1"),
    )

    assert investigation.candidate_id == "cand-1"


def test_a_terminal_investigation_needs_a_stop_reason() -> None:
    with pytest.raises(ValueError, match="needs a stop reason"):
        _investigation(status=InvestigationStatus.STOPPED)


def test_a_retry_links_back_to_the_previous_investigation() -> None:
    retry = _investigation(
        id=InvestigationId("inv-2"),
        previous_investigation_id=InvestigationId("inv-1"),
    )

    assert retry.previous_investigation_id == "inv-1"


def test_iterations_are_numbered_from_one() -> None:
    investigation = _investigation()
    iteration = investigation.begin_observation(_tick(1))

    assert iteration.number == 1
    assert investigation.current_iteration == 1
    assert investigation.current is iteration


def test_evidence_hashes_are_recorded_for_reproducibility() -> None:
    investigation = _run_to_reflecting(_investigation())
    iteration = investigation.iterations[0]

    assert iteration.evidence_before_hash == "hash-before"
    assert iteration.evidence_after_hash == "hash-after"


def test_the_delta_is_kept_on_the_iteration() -> None:
    investigation = _investigation()
    investigation.begin_observation(_tick(1))
    investigation.record_observation(_observation(), _tick(2))
    investigation.record_plan(_plan(), _tick(3))
    investigation.record_policy_decision(
        PolicyDecision.authorize("Allowed."), _tick(4), reserved_queries=4
    )
    delta = EvidenceDelta(added=(EvidenceType.INVENTORY_NUMBER,))
    investigation.record_tool_result(_tool_result(), "a", "b", delta, _tick(5))

    stored = investigation.iterations[0].evidence_delta
    assert stored is not None and stored.has_primary_inventory_evidence
