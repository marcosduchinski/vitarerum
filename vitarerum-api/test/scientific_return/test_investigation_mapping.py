"""Round-trip tests for the investigation mapping.

A repository's classic defect is a field that survives the write and is lost on
the read. These map an aggregate to its record and back without a database, so
the mapping is checked even where an integration run is unavailable.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.config import settings
from app.identity.public import PermissionId
from app.scientific_return.application.ports import ToolExecutionRecord
from app.scientific_return.domain.enums import (
    AgentProgress,
    AgentRecommendedAction,
    EvidenceType,
    InvestigationMode,
    InvestigationObjective,
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
    ObservedCandidate,
    ObservedObject,
    PolicyDecision,
    ProposedAction,
    ReasonerTelemetry,
    ToolResultSummary,
)
from app.scientific_return.domain.investigation_models import (
    InvestigationId,
    ScientificReturnInvestigation,
    ToolExecutionId,
)
from app.scientific_return.domain.models import (
    CandidatePublicationId,
    ScientificReturnRunId,
    ScientificReturnWatchId,
)
from app.scientific_return.infrastructure.repositories import (
    _investigation_to_domain,
    _investigation_to_record,
    _tool_execution_to_domain,
    _tool_execution_to_record,
)
from app.shared.field_encryption import FieldEncryptor

_NOW = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)


def _encryptor() -> FieldEncryptor:
    return FieldEncryptor.from_base64(settings.db_field_encryption_key)


def _tick(step: int) -> datetime:
    return _NOW + timedelta(seconds=step)


def _completed_investigation() -> ScientificReturnInvestigation:
    investigation = ScientificReturnInvestigation(
        id=InvestigationId("inv-1"),
        watch_id=ScientificReturnWatchId("watch-1"),
        objective=InvestigationObjective.ENRICH_CANDIDATE,
        mode=InvestigationMode.SUPERVISED,
        initial_run_id=ScientificReturnRunId("run-1"),
        budget=ExecutionBudget(1, 1, 4, 10, 5),
        created_by=PermissionId("perm-1"),
        started_at=_NOW,
        candidate_id=CandidatePublicationId("cand-1"),
        previous_investigation_id=InvestigationId("inv-0"),
        idempotency_key="client-key-1",
    )
    investigation.begin_observation(_tick(1))
    investigation.record_observation(
        _observation(), _tick(2)
    )
    investigation.record_plan(
        AgentPlan(
            objective="Find inventory evidence.",
            action=ProposedAction(
                AgentRecommendedAction.SEARCH_INVENTORY_VARIANTS, "object-1"
            ),
            reasoning_summary="No inventory evidence yet.",
            expected_evidence=(EvidenceType.INVENTORY_NUMBER,),
        ),
        _tick(3),
    )
    investigation.record_policy_decision(
        PolicyDecision.authorize("Four untried variants."),
        _tick(4),
        reserved_queries=4,
    )
    investigation.record_tool_result(
        ToolResultSummary(
            executed_queries=('"MB11-001283"',),
            sources=("EUROPE_PMC",),
            total_results=3,
            created_candidate_ids=("cand-9",),
        ),
        "hash-before",
        "hash-after",
        EvidenceDelta(
            added=(EvidenceType.INVENTORY_NUMBER,),
            preserved=(EvidenceType.AUTHOR,),
        ),
        _tick(5),
        tool_execution_id=ToolExecutionId("tool-1"),
    )
    investigation.record_telemetry(
        ReasonerTelemetry(
            model="llama3.1:8b",
            prompt_version="scientific-return-agent-plan-v1",
            plan_latency_ms=40413,
            reflection_latency_ms=140552,
            plan_response_hash="a" * 64,
            reflection_response_hash="b" * 64,
        )
    )
    investigation.record_reflection(
        AgentReflection(
            progress=AgentProgress.EVIDENCE_ADDED,
            evidence_delta_summary="One primary inventory evidence was added.",
            recommended_stop=True,
            reasoning_summary="Objective met.",
            remaining_gaps=("author confirmation",),
        )
    )
    investigation.present_for_review(StopReason.EVIDENCE_SUFFICIENT, _tick(6))
    return investigation


def _observation() -> AgentObservation:
    return AgentObservation(
        objective=InvestigationObjective.ENRICH_CANDIDATE,
        project_reference="PRJ-1",
        researcher="Rita P. Eusébio",
        objects=(ObservedObject("object-1", "MUHNAC/MB11-001283", "Trichoniscoides"),),
        tried_queries=('"MUHNAC/MB11-001283"',),
        allowed_actions=(AgentRecommendedAction.SEARCH_INVENTORY_VARIANTS,),
        budget=ExecutionBudget(1, 1, 4, 10, 5),
        candidate=ObservedCandidate("cand-1", "A title", "10.0/x"),
    )


def _roundtrip(
    investigation: ScientificReturnInvestigation,
) -> ScientificReturnInvestigation:
    encryptor = _encryptor()
    record = _investigation_to_record(investigation, encryptor)
    return _investigation_to_domain(record, encryptor)


def test_the_aggregate_survives_a_round_trip() -> None:
    original = _completed_investigation()

    restored = _roundtrip(original)

    assert restored.id == original.id
    assert restored.watch_id == original.watch_id
    assert restored.candidate_id == original.candidate_id
    assert restored.previous_investigation_id == original.previous_investigation_id
    assert restored.objective is original.objective
    assert restored.mode is original.mode
    assert restored.status is original.status
    assert restored.stop_reason is original.stop_reason
    assert restored.current_iteration == original.current_iteration
    assert restored.completed_at == original.completed_at
    assert restored.version == original.version


def test_the_budget_survives_with_its_consumption() -> None:
    original = _completed_investigation()

    restored = _roundtrip(original)

    assert restored.budget == original.budget
    assert restored.budget.used_queries == 4
    assert restored.budget.created_candidates == 1


def test_the_plan_survives_including_its_action_argument() -> None:
    restored = _roundtrip(_completed_investigation())
    plan = restored.iterations[0].plan

    assert plan is not None
    assert plan.action.type is AgentRecommendedAction.SEARCH_INVENTORY_VARIANTS
    assert plan.action.object_id == "object-1"
    assert plan.expected_evidence == (EvidenceType.INVENTORY_NUMBER,)
    assert plan.objective == "Find inventory evidence."


def test_the_reflection_survives() -> None:
    restored = _roundtrip(_completed_investigation())
    reflection = restored.iterations[0].reflection

    assert reflection is not None
    assert reflection.progress is AgentProgress.EVIDENCE_ADDED
    assert reflection.recommended_stop is True
    assert reflection.remaining_gaps == ("author confirmation",)


def test_the_policy_decision_survives() -> None:
    restored = _roundtrip(_completed_investigation())
    decision = restored.iterations[0].policy_decision

    assert decision is not None
    assert decision.authorized
    assert decision.justification == "Four untried variants."


def test_a_rejected_decision_keeps_its_typed_reason() -> None:
    investigation = ScientificReturnInvestigation(
        id=InvestigationId("inv-2"),
        watch_id=ScientificReturnWatchId("watch-1"),
        objective=InvestigationObjective.DISCOVER_CANDIDATE,
        mode=InvestigationMode.SUPERVISED,
        initial_run_id=ScientificReturnRunId("run-1"),
        budget=ExecutionBudget(1, 1, 4, 10, 5),
        created_by=PermissionId("perm-1"),
        started_at=_NOW,
    )
    investigation.begin_observation(_tick(1))
    investigation.record_observation(_observation_for_discovery(), _tick(2))
    investigation.record_plan(
        AgentPlan(
            objective="Search.",
            action=ProposedAction(
                AgentRecommendedAction.SEARCH_INVENTORY_VARIANTS, "object-1"
            ),
            reasoning_summary="Try variants.",
        ),
        _tick(3),
    )
    investigation.record_policy_decision(
        PolicyDecision.reject(
            PolicyRejectionReason.NO_NEW_QUERY_VARIANT, "All tried."
        ),
        _tick(4),
    )

    decision = _roundtrip(investigation).iterations[0].policy_decision

    assert decision is not None
    assert not decision.authorized
    assert decision.rejection_reason is PolicyRejectionReason.NO_NEW_QUERY_VARIANT


def _observation_for_discovery() -> AgentObservation:
    return AgentObservation(
        objective=InvestigationObjective.DISCOVER_CANDIDATE,
        project_reference="PRJ-1",
        researcher="Rita P. Eusébio",
        objects=(ObservedObject("object-1", "MUHNAC/MB11-001283", "Trichoniscoides"),),
        tried_queries=(),
        allowed_actions=(AgentRecommendedAction.SEARCH_INVENTORY_VARIANTS,),
        budget=ExecutionBudget(1, 1, 4, 10, 5),
    )


def test_the_evidence_delta_and_hashes_survive() -> None:
    iteration = _roundtrip(_completed_investigation()).iterations[0]

    assert iteration.evidence_before_hash == "hash-before"
    assert iteration.evidence_after_hash == "hash-after"
    delta = iteration.evidence_delta
    assert delta is not None
    assert delta.added == (EvidenceType.INVENTORY_NUMBER,)
    assert delta.preserved == (EvidenceType.AUTHOR,)
    assert delta.has_primary_inventory_evidence


def test_the_iteration_keeps_its_status_and_tool_execution() -> None:
    iteration = _roundtrip(_completed_investigation()).iterations[0]

    assert iteration.status is IterationStatus.COMPLETED
    assert iteration.tool_execution_id == "tool-1"
    assert iteration.number == 1


def test_the_plan_and_reflection_are_encrypted_at_rest() -> None:
    """They carry project data and model output, like the snapshot payload."""
    record = _investigation_to_record(_completed_investigation(), _encryptor())
    stored = record.iterations[0]

    assert stored.plan_payload is not None
    assert "Find inventory evidence." not in stored.plan_payload
    assert stored.reflection_payload is not None
    assert "primary inventory evidence" not in stored.reflection_payload


def test_a_tool_execution_survives_a_round_trip() -> None:
    encryptor = _encryptor()
    original = ToolExecutionRecord(
        id=ToolExecutionId("tool-1"),
        investigation_id=InvestigationId("inv-1"),
        iteration_id="inv-1:1",
        idempotency_key="key-1",
        action=AgentRecommendedAction.SEARCH_INVENTORY_VARIANTS,
        started_at=_NOW,
        queries=('"MB11-001283"', '"MNHNC:MB11:001283"'),
        sources=("EUROPE_PMC", "CROSSREF"),
        total_results=7,
        created_candidate_ids=("cand-9",),
        added_evidence_ids=("ev-1", "ev-2"),
        result_hash="abc",
        succeeded=True,
        attempts=2,
        completed_at=_tick(9),
    )

    restored = _tool_execution_to_domain(
        _tool_execution_to_record(original, encryptor), encryptor
    )

    assert restored == original


def test_the_issued_queries_are_encrypted_at_rest() -> None:
    record = _tool_execution_to_record(
        ToolExecutionRecord(
            id=ToolExecutionId("tool-1"),
            investigation_id=InvestigationId("inv-1"),
            iteration_id="inv-1:1",
            idempotency_key="key-1",
            action=AgentRecommendedAction.SEARCH_INVENTORY_VARIANTS,
            started_at=_NOW,
            queries=("MB11-001283",),
        ),
        _encryptor(),
    )

    assert record.queries_payload is not None
    assert "MB11-001283" not in record.queries_payload


def test_the_observation_survives_a_round_trip() -> None:
    """The plan requires the observation in the trajectory, and the UI shows it."""
    observation = _roundtrip(_completed_investigation()).iterations[0].observation

    assert observation is not None
    assert observation.researcher == "Rita P. Eusébio"
    assert observation.tried_queries == ('"MUHNAC/MB11-001283"',)
    assert observation.objects[0].inventory_number == "MUHNAC/MB11-001283"
    assert observation.candidate is not None
    assert observation.candidate.candidate_id == "cand-1"


def test_the_observation_is_encrypted_at_rest() -> None:
    record = _investigation_to_record(_completed_investigation(), _encryptor())
    stored = record.iterations[0]

    assert stored.observation_payload is not None
    assert "MUHNAC/MB11-001283" not in stored.observation_payload


def test_the_telemetry_survives_a_round_trip() -> None:
    """Which model and prompt produced a proposal is part of the audit trail."""
    original = _completed_investigation()

    restored = _roundtrip(original)

    assert restored.iterations[0].telemetry == original.iterations[0].telemetry


def test_the_client_idempotency_key_survives_a_round_trip() -> None:
    original = _completed_investigation()

    assert _roundtrip(original).idempotency_key == original.idempotency_key
