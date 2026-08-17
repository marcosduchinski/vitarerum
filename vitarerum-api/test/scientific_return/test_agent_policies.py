from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.scientific_return.domain.agent_policies import (
    ActionPolicyContext,
    AgentActionPolicy,
    AgentStopPolicy,
    AuthorizedExecution,
    StopPolicyContext,
)
from app.scientific_return.domain.enums import (
    AgentProgress,
    AgentRecommendedAction,
    CandidateStatus,
    EvidenceStrength,
    EvidenceType,
    InvestigationMode,
    InvestigationObjective,
    InvestigationStatus,
    PolicyRejectionReason,
    StopReason,
)
from app.scientific_return.domain.evidence_delta import (
    calculate_evidence_delta,
    evidence_hash,
)
from app.scientific_return.domain.inventory_variants import (
    generate_inventory_query_variants,
)
from app.scientific_return.domain.investigation_contracts import (
    AgentReflection,
    EvidenceDelta,
    ExecutionBudget,
    ObservedObject,
    PolicyDecision,
    ProposedAction,
    ToolResultSummary,
)
from app.scientific_return.domain.models import (
    CandidateEvidence,
    CandidateEvidenceId,
    CandidatePublicationId,
)

_NOW = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)
_SEARCH = AgentRecommendedAction.SEARCH_INVENTORY_VARIANTS


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


def _context(**overrides: object) -> ActionPolicyContext:
    values: dict[str, object] = {
        "objective": InvestigationObjective.DISCOVER_CANDIDATE,
        "mode": InvestigationMode.SUPERVISED,
        "status": InvestigationStatus.VALIDATING,
        "budget": _budget(),
        "objects": (
            ObservedObject("object-1", "MUHNAC/MB06-005747", "Cynoscion regalis"),
        ),
        "allowed_actions": frozenset({_SEARCH}),
        "allowed_sources": ("CROSSREF", "EUROPE_PMC"),
    }
    values.update(overrides)
    return ActionPolicyContext(**values)  # type: ignore[arg-type]


def _evaluate(
    action: ProposedAction | None = None, **overrides: object
) -> tuple[PolicyDecision, AuthorizedExecution | None]:
    outcome = AgentActionPolicy().evaluate(
        action or ProposedAction(_SEARCH, "object-1"), _context(**overrides)
    )
    return outcome.decision, outcome.execution


def _evidence(
    evidence_type: EvidenceType, value: str = "v", object_id: str = "object-1"
) -> CandidateEvidence:
    return CandidateEvidence(
        id=CandidateEvidenceId("e-1"),
        candidate_id=CandidatePublicationId("cand-1"),
        type=evidence_type,
        strength=EvidenceStrength.PRIMARY,
        value=value,
        source_field="title_or_abstract",
        explanation="x",
        created_at=_NOW,
        object_id=object_id,
    )


# --- action policy: the happy path ------------------------------------------


def test_an_allowed_action_is_authorized_with_derived_queries() -> None:
    decision, execution = _evaluate()

    assert decision.authorized
    assert execution is not None
    assert execution.object_id == "object-1"
    assert execution.result_limit == 10
    assert execution.query_count == 4


def test_the_policy_derives_the_queries_the_model_never_supplied() -> None:
    """The model asked only for an object; every query string comes from here."""
    _, execution = _evaluate()

    assert execution is not None
    texts = [variant.text for variant in execution.queries]
    assert "MB06-005747" in texts
    assert all("MB06" in text or "MUHNAC" in text or "MNHN" in text for text in texts)


def test_europe_pmc_is_routed_first() -> None:
    """It is the only full-text source, and inventory numbers live in full text."""
    _, execution = _evaluate()

    assert execution is not None
    assert execution.sources[0] == "EUROPE_PMC"


def test_only_sources_that_honour_an_exact_phrase_are_routed_to() -> None:
    """Crossref ranks by relevance and never returns nothing, so an inventory
    code sent there yields noise. Measured against the live API."""
    _, execution = _evaluate(allowed_sources=("CROSSREF", "EUROPE_PMC", "ZENODO"))

    assert execution is not None
    assert execution.sources == ("EUROPE_PMC",)


def test_a_configuration_with_no_exact_match_source_is_refused() -> None:
    decision, execution = _evaluate(allowed_sources=("CROSSREF",))

    assert decision.rejection_reason is PolicyRejectionReason.SOURCE_NOT_ALLOWED
    assert execution is None


def test_the_query_budget_caps_the_number_of_variants() -> None:
    _, execution = _evaluate(budget=_budget(max_queries=2))

    assert execution is not None
    assert execution.query_count == 2


# --- action policy: refusals -------------------------------------------------


def test_an_action_outside_the_allowlist_is_refused() -> None:
    decision, execution = _evaluate(
        ProposedAction(AgentRecommendedAction.SEARCH_FULL_TEXT, "object-1")
    )

    assert not decision.authorized
    assert decision.rejection_reason is PolicyRejectionReason.ACTION_NOT_ALLOWED
    assert execution is None


def test_an_allowlisted_action_without_an_executor_is_still_refused() -> None:
    """Configuration cannot enable something the increment cannot run."""
    decision, _ = _evaluate(
        ProposedAction(AgentRecommendedAction.SEARCH_AUTHOR_VARIANTS, "object-1"),
        allowed_actions=frozenset(
            {_SEARCH, AgentRecommendedAction.SEARCH_AUTHOR_VARIANTS}
        ),
    )

    assert decision.rejection_reason is PolicyRejectionReason.ACTION_NOT_ALLOWED


def test_an_object_outside_the_snapshot_is_refused() -> None:
    decision, execution = _evaluate(ProposedAction(_SEARCH, "object-from-elsewhere"))

    assert decision.rejection_reason is PolicyRejectionReason.OBJECT_NOT_IN_SNAPSHOT
    assert execution is None


def test_an_object_without_an_inventory_number_is_refused() -> None:
    decision, _ = _evaluate(
        objects=(ObservedObject("object-1", "   ", "Cynoscion regalis"),)
    )

    assert decision.rejection_reason is PolicyRejectionReason.INVENTORY_MISSING


def test_no_configured_source_is_refused() -> None:
    decision, _ = _evaluate(allowed_sources=())

    assert decision.rejection_reason is PolicyRejectionReason.SOURCE_NOT_ALLOWED


def test_an_exhausted_query_budget_is_refused() -> None:
    decision, _ = _evaluate(
        budget=_budget(max_iterations=2).reserve_action(queries=4)
    )

    assert decision.rejection_reason is PolicyRejectionReason.BUDGET_EXHAUSTED


def test_a_reached_candidate_ceiling_is_refused() -> None:
    decision, _ = _evaluate(
        budget=_budget(max_iterations=2, max_new_candidates=1).record_candidates(1)
    )

    assert decision.rejection_reason is PolicyRejectionReason.CANDIDATE_LIMIT_REACHED


def test_a_mode_that_does_not_execute_is_refused() -> None:
    decision, _ = _evaluate(mode=InvestigationMode.POLICY_ONLY)

    assert decision.rejection_reason is PolicyRejectionReason.MODE_FORBIDS_EXECUTION


def test_a_candidate_decided_during_the_cycle_stops_everything() -> None:
    decision, _ = _evaluate(candidate_status=CandidateStatus.CONFIRMED)

    assert decision.rejection_reason is PolicyRejectionReason.CANDIDATE_ALREADY_DECIDED


def test_a_state_other_than_validating_is_refused() -> None:
    decision, _ = _evaluate(status=InvestigationStatus.EXECUTING)

    assert (
        decision.rejection_reason
        is PolicyRejectionReason.INVESTIGATION_NOT_ACTIONABLE
    )


def test_exhausting_every_variant_is_refused() -> None:
    """With nothing new to ask, the cycle must refuse instead of contacting a source."""
    every_variant = tuple(
        variant.text
        for variant in generate_inventory_query_variants("MUHNAC/MB06-005747")
    )
    decision, execution = _evaluate(tried_queries=every_variant)

    assert decision.rejection_reason is PolicyRejectionReason.NO_NEW_QUERY_VARIANT
    assert execution is None


def test_the_deterministic_query_alone_still_leaves_work_to_do() -> None:
    """The exact form is what the pipeline already tried; the variants are the point."""
    decision, execution = _evaluate(tried_queries=('"MUHNAC/MB06-005747"',))

    assert decision.authorized
    assert execution is not None
    texts = [variant.text for variant in execution.queries]
    assert "MUHNAC/MB06-005747" not in texts
    assert "MB06-005747" in texts


# --- action policy: the terminating actions ----------------------------------


@pytest.mark.parametrize(
    "action",
    [
        AgentRecommendedAction.PRESENT_FOR_REVIEW,
        AgentRecommendedAction.STOP_INSUFFICIENT_EVIDENCE,
    ],
)
def test_terminating_actions_need_no_allowlist_entry(
    action: AgentRecommendedAction,
) -> None:
    """Otherwise a misconfigured allowlist leaves no legal way to end."""
    decision, execution = _evaluate(
        ProposedAction(action), allowed_actions=frozenset()
    )

    assert decision.authorized
    assert execution is None


def test_terminating_actions_still_obey_a_human_decision() -> None:
    decision, _ = _evaluate(
        ProposedAction(AgentRecommendedAction.PRESENT_FOR_REVIEW),
        candidate_status=CandidateStatus.DISMISSED,
    )

    assert decision.rejection_reason is PolicyRejectionReason.CANDIDATE_ALREADY_DECIDED


def test_a_terminating_action_is_allowed_in_a_non_executing_mode() -> None:
    decision, _ = _evaluate(
        ProposedAction(AgentRecommendedAction.STOP_INSUFFICIENT_EVIDENCE),
        mode=InvestigationMode.POLICY_ONLY,
    )

    assert decision.authorized


# --- stop policy -------------------------------------------------------------


def _stop(**overrides: object) -> StopPolicyContext:
    values: dict[str, object] = {
        "objective": InvestigationObjective.DISCOVER_CANDIDATE,
        "budget": _budget(),
    }
    values.update(overrides)
    return StopPolicyContext(**values)  # type: ignore[arg-type]


def _result(**overrides: object) -> ToolResultSummary:
    values: dict[str, object] = {
        "executed_queries": ("MB06-005747",),
        "sources": ("CROSSREF",),
        "total_results": 3,
    }
    values.update(overrides)
    return ToolResultSummary(**values)  # type: ignore[arg-type]


def test_new_evidence_ends_the_cycle_as_sufficient() -> None:
    decision = AgentStopPolicy().decide(
        _stop(
            tool_result=_result(),
            delta=EvidenceDelta(added=(EvidenceType.INVENTORY_NUMBER,)),
            has_reviewable_candidate=True,
        )
    )

    assert decision.reason is StopReason.EVIDENCE_SUFFICIENT
    assert decision.awaiting_human_review


def test_a_created_candidate_ends_the_cycle_as_sufficient() -> None:
    decision = AgentStopPolicy().decide(
        _stop(
            tool_result=_result(created_candidate_ids=("cand-9",)),
            delta=EvidenceDelta(),
            has_reviewable_candidate=True,
        )
    )

    assert decision.reason is StopReason.EVIDENCE_SUFFICIENT


def test_no_results_ends_without_a_candidate() -> None:
    decision = AgentStopPolicy().decide(
        _stop(tool_result=_result(total_results=0), delta=EvidenceDelta())
    )

    assert decision.reason is StopReason.NO_RESULTS
    assert not decision.awaiting_human_review


def test_results_without_evidence_end_as_no_evidence_added() -> None:
    decision = AgentStopPolicy().decide(
        _stop(tool_result=_result(), delta=EvidenceDelta())
    )

    assert decision.reason is StopReason.NO_EVIDENCE_ADDED


def test_a_rejected_action_maps_its_reason_to_a_stop_reason() -> None:
    decision = AgentStopPolicy().decide(
        _stop(
            decision=PolicyDecision.reject(
                PolicyRejectionReason.NO_NEW_QUERY_VARIANT, "All tried."
            )
        )
    )

    assert decision.reason is StopReason.QUERY_REPEATED


def test_an_unmapped_rejection_falls_back_to_action_rejected() -> None:
    decision = AgentStopPolicy().decide(
        _stop(
            decision=PolicyDecision.reject(
                PolicyRejectionReason.OBJECT_NOT_IN_SNAPSHOT, "Not ours."
            )
        )
    )

    assert decision.reason is StopReason.ACTION_REJECTED


def test_an_unavailable_source_is_distinguished_from_a_failing_one() -> None:
    unavailable = AgentStopPolicy().decide(_stop(tool_unavailable=True))
    failed = AgentStopPolicy().decide(_stop(tool_error="503 from Crossref"))

    assert unavailable.reason is StopReason.TOOL_UNAVAILABLE
    assert failed.reason is StopReason.TOOL_FAILED


def test_a_requested_review_is_recorded_as_such() -> None:
    decision = AgentStopPolicy().decide(
        _stop(
            proposed_action=AgentRecommendedAction.PRESENT_FOR_REVIEW,
            has_reviewable_candidate=True,
        )
    )

    assert decision.reason is StopReason.PRESENTED_FOR_REVIEW
    assert decision.awaiting_human_review


def test_a_requested_stop_is_recorded_as_insufficient_evidence() -> None:
    decision = AgentStopPolicy().decide(
        _stop(proposed_action=AgentRecommendedAction.STOP_INSUFFICIENT_EVIDENCE)
    )

    assert decision.reason is StopReason.INSUFFICIENT_EVIDENCE


def test_a_human_decision_during_the_cycle_outranks_everything() -> None:
    decision = AgentStopPolicy().decide(
        _stop(
            candidate_decided=True,
            has_reviewable_candidate=True,
            tool_result=_result(),
            delta=EvidenceDelta(added=(EvidenceType.INVENTORY_NUMBER,)),
        )
    )

    assert decision.reason is StopReason.CANDIDATE_ALREADY_DECIDED
    assert not decision.awaiting_human_review


def test_an_iteration_that_did_nothing_ends_as_no_progress() -> None:
    decision = AgentStopPolicy().decide(_stop())

    assert decision.reason is StopReason.NO_PROGRESS


def test_the_model_recommendation_does_not_decide() -> None:
    """recommendedStop is advisory; the policy reads the measured delta."""
    reflection = AgentReflection(
        progress=AgentProgress.NO_NEW_EVIDENCE,
        evidence_delta_summary="Nothing.",
        recommended_stop=False,
        reasoning_summary="Let me keep going.",
    )
    decision = AgentStopPolicy().decide(
        _stop(
            reflection=reflection,
            tool_result=_result(),
            delta=EvidenceDelta(added=(EvidenceType.INVENTORY_NUMBER,)),
            has_reviewable_candidate=True,
        )
    )

    assert decision.reason is StopReason.EVIDENCE_SUFFICIENT


def test_every_stop_reason_used_by_the_policy_is_typed() -> None:
    """No path may leave an investigation without a reason."""
    contexts = [
        _stop(),
        _stop(candidate_decided=True),
        _stop(tool_unavailable=True),
        _stop(tool_error="boom"),
        _stop(tool_result=_result(total_results=0)),
        _stop(tool_result=_result(), delta=EvidenceDelta()),
        _stop(proposed_action=AgentRecommendedAction.PRESENT_FOR_REVIEW),
    ]

    for context in contexts:
        assert isinstance(AgentStopPolicy().decide(context).reason, StopReason)


# --- evidence delta ----------------------------------------------------------


def test_added_evidence_is_detected() -> None:
    before = [_evidence(EvidenceType.AUTHOR)]
    after = [_evidence(EvidenceType.AUTHOR), _evidence(EvidenceType.INVENTORY_NUMBER)]

    delta = calculate_evidence_delta(before, after)

    assert delta.added == (EvidenceType.INVENTORY_NUMBER,)
    assert delta.preserved == (EvidenceType.AUTHOR,)
    assert delta.removed == ()
    assert delta.has_primary_inventory_evidence


def test_the_same_finding_from_a_new_run_is_not_a_change() -> None:
    """Row ids and timestamps differ between runs; the finding does not."""
    before = [_evidence(EvidenceType.AUTHOR)]
    after = [_evidence(EvidenceType.AUTHOR)]
    after[0].id = CandidateEvidenceId("different-row")
    after[0].created_at = datetime(2027, 1, 1, tzinfo=UTC)

    delta = calculate_evidence_delta(before, after)

    assert delta.added == ()
    assert delta.preserved == (EvidenceType.AUTHOR,)


def test_lost_evidence_is_reported_rather_than_hidden() -> None:
    delta = calculate_evidence_delta([_evidence(EvidenceType.AUTHOR)], [])

    assert delta.removed == (EvidenceType.AUTHOR,)


def test_the_hash_is_stable_and_order_independent() -> None:
    a = _evidence(EvidenceType.AUTHOR, "one")
    b = _evidence(EvidenceType.INVENTORY_NUMBER, "two")

    assert evidence_hash([a, b]) == evidence_hash([b, a])
    assert evidence_hash([a]) != evidence_hash([a, b])
    assert evidence_hash([]) == evidence_hash([])
