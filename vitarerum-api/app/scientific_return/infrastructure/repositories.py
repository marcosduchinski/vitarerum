from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Any, cast

from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.elements import ColumnElement

from app.scientific_return.application.agent_contracts import AGENT_CONTRACT_VERSION
from app.scientific_return.application.ports import (
    FULL_AGENTIC_READER_PROMPT_ID_PREFIX,
    CandidateReviewItem,
    ScientificReturnMetrics,
    ToolExecutionRecord,
)
from app.scientific_return.domain.enums import (
    AgentAnalysisStatus,
    AgentConfidence,
    AgentProgress,
    AgentRecommendedAction,
    CandidateStatus,
    EvidenceSourceField,
    EvidenceStrength,
    EvidenceType,
    InventoryEvidenceStatus,
    InvestigationObjective,
    InvestigationStatus,
    RunKind,
    RunStatus,
    WatchStatus,
)
from app.scientific_return.domain.evidence_delta import (
    evidence_identity as _evidence_identity,
)
from app.scientific_return.domain.full_agentic_models import (
    CandidateDecisionContext,
    GroundedInventoryForm,
    KnowledgeItemId,
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
    InvestigationIteration,
    InvestigationIterationId,
    ScientificReturnInvestigation,
    ToolExecutionId,
)
from app.scientific_return.domain.models import (
    CandidateAgentAnalysis,
    CandidateAgentAnalysisId,
    CandidateAnalysisResult,
    CandidateCorrection,
    CandidateDecision,
    CandidateDecisionId,
    CandidateEvidence,
    CandidateEvidenceId,
    CandidatePublication,
    CandidatePublicationId,
    ConsultedObjectSnapshot,
    ProjectSnapshotPayload,
    ScientificReturnProjectSnapshot,
    ScientificReturnQuery,
    ScientificReturnQueryId,
    ScientificReturnRunId,
    ScientificReturnSearchRun,
    ScientificReturnSnapshotId,
    ScientificReturnWatch,
    ScientificReturnWatchId,
)
from app.scientific_return.infrastructure.models import (
    AgenticInvestigationCandidateRecord,
    CandidateAgentAnalysisRecord,
    CandidateDecisionRecord,
    CandidateEvidenceRecord,
    CandidatePublicationRecord,
    ScientificReturnInvestigationRecord,
    ScientificReturnIterationRecord,
    ScientificReturnQueryRecord,
    ScientificReturnRunRecord,
    ScientificReturnSnapshotRecord,
    ScientificReturnToolExecutionRecord,
    ScientificReturnWatchRecord,
)
from app.shared.field_encryption import FieldEncryptor
from app.shared.kernel import PermissionId

_SNAPSHOT_PAYLOAD = "scientific_return_snapshots.payload"
_QUERY_TEXT = "scientific_return_queries.query_text"
_AGENT_INPUT = "scientific_return_agent_analyses.input_payload"
_AGENT_ANALYSIS = "scientific_return_agent_analyses.analysis_payload"
_DECISION_CONTEXT = "scientific_return_decisions.decision_context"
_ITERATION_OBSERVATION = "scientific_return_agent_iterations.observation_payload"
_ITERATION_PLAN = "scientific_return_agent_iterations.plan_payload"
_ITERATION_REFLECTION = "scientific_return_agent_iterations.reflection_payload"
_TOOL_QUERIES = "scientific_return_agent_tool_executions.queries_payload"
_TERMINAL_STATUSES = (
    InvestigationStatus.AWAITING_HUMAN_REVIEW,
    InvestigationStatus.STOPPED,
    InvestigationStatus.FAILED,
)


def _payload_to_dict(payload: ProjectSnapshotPayload) -> dict[str, object]:
    return asdict(payload)


def _payload_to_domain(payload: dict[str, object]) -> ProjectSnapshotPayload:
    raw_objects = cast(list[dict[str, object]], payload.get("consulted_objects", []))
    objects = tuple(
        ConsultedObjectSnapshot(
            id=str(item["id"]),
            inventory_number=str(item["inventory_number"]),
            object_name=str(item["object_name"]),
        )
        for item in raw_objects
        if isinstance(item, dict)
    )
    return ProjectSnapshotPayload(
        project_id=str(payload["project_id"]),
        project_reference=str(payload["project_reference"]),
        researcher=str(payload["researcher"]),
        consulted_objects=objects,
    )


def _watch_to_domain(record: ScientificReturnWatchRecord) -> ScientificReturnWatch:
    return ScientificReturnWatch(
        id=ScientificReturnWatchId(record.id),
        project_id=record.project_id,
        status=record.status,
        review_interval_days=record.review_interval_days,
        created_by=PermissionId(record.created_by),
        created_at=record.created_at,
        last_run_at=record.last_run_at,
        next_run_at=record.next_run_at,
        project_snapshot_id=ScientificReturnSnapshotId(record.project_snapshot_id),
    )


def _run_to_domain(record: ScientificReturnRunRecord) -> ScientificReturnSearchRun:
    return ScientificReturnSearchRun(
        id=ScientificReturnRunId(record.id),
        watch_id=ScientificReturnWatchId(record.watch_id),
        status=record.status,
        started_at=record.started_at,
        completed_at=record.completed_at,
        source_count=record.source_count,
        candidate_count=record.candidate_count,
        new_candidate_count=record.new_candidate_count,
        error_message=record.error_message,
        run_kind=record.run_kind,
    )


def _query_to_domain(
    record: ScientificReturnQueryRecord, encryptor: FieldEncryptor
) -> ScientificReturnQuery:
    return ScientificReturnQuery(
        id=ScientificReturnQueryId(record.id),
        run_id=ScientificReturnRunId(record.run_id),
        source=record.source,
        query_text=encryptor.decrypt_text(record.query_text, _QUERY_TEXT) or "",
        query_type=record.query_type,
        sent_at=record.sent_at,
        result_count=record.result_count,
        status=record.status,
        error_message=record.error_message,
    )


def _evidence_to_domain(record: CandidateEvidenceRecord) -> CandidateEvidence:
    return CandidateEvidence(
        id=CandidateEvidenceId(record.id),
        candidate_id=CandidatePublicationId(record.candidate_id),
        type=record.type,
        strength=record.strength,
        value=record.value,
        source_field=record.source_field,
        explanation=record.explanation,
        created_at=record.created_at,
        object_id=record.object_id,
        investigation_id=record.investigation_id,
        iteration_id=record.iteration_id,
        tool_execution_id=record.tool_execution_id,
        query_id=record.query_id,
        source_record_id=record.source_record_id,
        content_hash=record.content_hash,
    )


def _budget_to_json(budget: ExecutionBudget) -> dict[str, Any]:
    return {
        "maxIterations": budget.max_iterations,
        "maxActions": budget.max_actions,
        "maxQueries": budget.max_queries,
        "maxResultsPerQuery": budget.max_results_per_query,
        "maxNewCandidates": budget.max_new_candidates,
        "usedIterations": budget.used_iterations,
        "usedActions": budget.used_actions,
        "usedQueries": budget.used_queries,
        "createdCandidates": budget.created_candidates,
    }


def _budget_to_domain(payload: dict[str, Any]) -> ExecutionBudget:
    return ExecutionBudget(
        max_iterations=int(payload["maxIterations"]),
        max_actions=int(payload["maxActions"]),
        max_queries=int(payload["maxQueries"]),
        max_results_per_query=int(payload["maxResultsPerQuery"]),
        max_new_candidates=int(payload["maxNewCandidates"]),
        used_iterations=int(payload.get("usedIterations", 0)),
        used_actions=int(payload.get("usedActions", 0)),
        used_queries=int(payload.get("usedQueries", 0)),
        created_candidates=int(payload.get("createdCandidates", 0)),
    )


def _delta_to_json(delta: EvidenceDelta | None) -> dict[str, Any] | None:
    if delta is None:
        return None
    return {
        "added": [item.value for item in delta.added],
        "preserved": [item.value for item in delta.preserved],
        "removed": [item.value for item in delta.removed],
    }


def _delta_to_domain(payload: dict[str, Any] | None) -> EvidenceDelta | None:
    if payload is None:
        return None
    return EvidenceDelta(
        added=tuple(EvidenceType(item) for item in payload.get("added", [])),
        preserved=tuple(EvidenceType(item) for item in payload.get("preserved", [])),
        removed=tuple(EvidenceType(item) for item in payload.get("removed", [])),
    )


def _reflection_to_json(reflection: AgentReflection | None) -> dict[str, Any] | None:
    if reflection is None:
        return None
    return {
        "progress": reflection.progress.value,
        "evidenceDeltaSummary": reflection.evidence_delta_summary,
        "remainingGaps": list(reflection.remaining_gaps),
        "recommendedStop": reflection.recommended_stop,
        "reasoningSummary": reflection.reasoning_summary,
    }


def _reflection_to_domain(payload: dict[str, Any] | None) -> AgentReflection | None:
    if payload is None:
        return None
    return AgentReflection(
        progress=AgentProgress(payload["progress"]),
        evidence_delta_summary=payload["evidenceDeltaSummary"],
        recommended_stop=bool(payload["recommendedStop"]),
        reasoning_summary=payload["reasoningSummary"],
        remaining_gaps=tuple(payload.get("remainingGaps", [])),
    )


def _observation_to_json(
    observation: AgentObservation | None,
) -> dict[str, Any] | None:
    if observation is None:
        return None
    candidate = observation.candidate
    return {
        "objective": observation.objective.value,
        "projectReference": observation.project_reference,
        "researcher": observation.researcher,
        "objects": [
            {
                "objectId": item.object_id,
                "inventoryNumber": item.inventory_number,
                "objectName": item.object_name,
            }
            for item in observation.objects
        ],
        "triedQueries": list(observation.tried_queries),
        "allowedActions": [item.value for item in observation.allowed_actions],
        "budget": _budget_to_json(observation.budget),
        "candidate": (
            None
            if candidate is None
            else {
                "candidateId": candidate.candidate_id,
                "title": candidate.title,
                "doi": candidate.doi,
                "verifiedEvidenceTypes": [
                    item.value for item in candidate.verified_evidence_types
                ],
            }
        ),
    }


def _observation_to_domain(
    payload: dict[str, Any] | None,
) -> AgentObservation | None:
    if payload is None:
        return None
    candidate = payload.get("candidate")
    return AgentObservation(
        objective=InvestigationObjective(payload["objective"]),
        project_reference=payload["projectReference"],
        researcher=payload["researcher"],
        objects=tuple(
            ObservedObject(
                object_id=item["objectId"],
                inventory_number=item["inventoryNumber"],
                object_name=item["objectName"],
            )
            for item in payload["objects"]
        ),
        tried_queries=tuple(payload.get("triedQueries", [])),
        allowed_actions=tuple(
            AgentRecommendedAction(item) for item in payload["allowedActions"]
        ),
        budget=_budget_to_domain(payload["budget"]),
        candidate=(
            None
            if candidate is None
            else ObservedCandidate(
                candidate_id=candidate["candidateId"],
                title=candidate["title"],
                doi=candidate["doi"],
                verified_evidence_types=tuple(
                    EvidenceType(item)
                    for item in candidate.get("verifiedEvidenceTypes", [])
                ),
            )
        ),
    )


def _plan_to_json(plan: AgentPlan | None) -> dict[str, Any] | None:
    if plan is None:
        return None
    return {
        "objective": plan.objective,
        "action": {
            "type": plan.action.type.value,
            "arguments": (
                {"objectId": plan.action.object_id} if plan.action.object_id else {}
            ),
        },
        "reasoningSummary": plan.reasoning_summary,
        "expectedEvidence": [item.value for item in plan.expected_evidence],
    }


def _plan_to_domain(payload: dict[str, Any] | None) -> AgentPlan | None:
    if payload is None:
        return None
    action = payload["action"]
    return AgentPlan(
        objective=payload["objective"],
        action=ProposedAction(
            type=AgentRecommendedAction(action["type"]),
            object_id=action.get("arguments", {}).get("objectId"),
        ),
        reasoning_summary=payload["reasoningSummary"],
        expected_evidence=tuple(
            EvidenceType(item) for item in payload.get("expectedEvidence", [])
        ),
    )


def _iteration_to_record(
    iteration: InvestigationIteration, encryptor: FieldEncryptor
) -> ScientificReturnIterationRecord:
    decision = iteration.policy_decision
    reflection = iteration.reflection
    telemetry = iteration.telemetry
    return ScientificReturnIterationRecord(
        id=iteration.id,
        investigation_id=iteration.investigation_id,
        number=iteration.number,
        status=iteration.status,
        observation_payload=encryptor.encrypt_json(
            _observation_to_json(iteration.observation), _ITERATION_OBSERVATION
        ),
        plan_payload=encryptor.encrypt_json(
            _plan_to_json(iteration.plan), _ITERATION_PLAN
        ),
        reflection_payload=encryptor.encrypt_json(
            _reflection_to_json(reflection), _ITERATION_REFLECTION
        ),
        policy_authorized=None if decision is None else decision.authorized,
        policy_rejection_reason=(
            None if decision is None else decision.rejection_reason
        ),
        policy_justification=None if decision is None else decision.justification,
        progress=None if reflection is None else reflection.progress,
        tool_execution_id=iteration.tool_execution_id,
        evidence_before_hash=iteration.evidence_before_hash,
        evidence_after_hash=iteration.evidence_after_hash,
        evidence_delta=_delta_to_json(iteration.evidence_delta),
        model=None if telemetry is None else telemetry.model,
        prompt_version=None if telemetry is None else telemetry.prompt_version,
        plan_latency_ms=None if telemetry is None else telemetry.plan_latency_ms,
        reflection_latency_ms=(
            None if telemetry is None else telemetry.reflection_latency_ms
        ),
        plan_response_hash=(
            None if telemetry is None else telemetry.plan_response_hash
        ),
        reflection_response_hash=(
            None if telemetry is None else telemetry.reflection_response_hash
        ),
        error_message=iteration.error_message,
        started_at=iteration.started_at,
        completed_at=iteration.completed_at,
    )


def _iteration_to_domain(
    record: ScientificReturnIterationRecord, encryptor: FieldEncryptor
) -> InvestigationIteration:
    decision = (
        None
        if record.policy_authorized is None
        else PolicyDecision(
            authorized=record.policy_authorized,
            justification=record.policy_justification or "-",
            rejection_reason=record.policy_rejection_reason,
        )
    )
    return InvestigationIteration(
        id=InvestigationIterationId(record.id),
        investigation_id=InvestigationId(record.investigation_id),
        number=record.number,
        started_at=record.started_at,
        status=record.status,
        observation=_observation_to_domain(
            cast(
                "dict[str, Any] | None",
                encryptor.decrypt_json(
                    record.observation_payload, _ITERATION_OBSERVATION
                ),
            )
        ),
        plan=_plan_to_domain(
            cast(
                "dict[str, Any] | None",
                encryptor.decrypt_json(record.plan_payload, _ITERATION_PLAN),
            )
        ),
        policy_decision=decision,
        tool_execution_id=(
            ToolExecutionId(record.tool_execution_id)
            if record.tool_execution_id
            else None
        ),
        evidence_before_hash=record.evidence_before_hash,
        evidence_after_hash=record.evidence_after_hash,
        evidence_delta=_delta_to_domain(record.evidence_delta),
        reflection=_reflection_to_domain(
            cast(
                "dict[str, Any] | None",
                encryptor.decrypt_json(
                    record.reflection_payload, _ITERATION_REFLECTION
                ),
            )
        ),
        telemetry=(
            None
            if record.model is None
            else ReasonerTelemetry(
                model=record.model,
                prompt_version=record.prompt_version or "",
                plan_latency_ms=record.plan_latency_ms or 0,
                reflection_latency_ms=record.reflection_latency_ms or 0,
                plan_response_hash=record.plan_response_hash or "",
                reflection_response_hash=record.reflection_response_hash or "",
            )
        ),
        error_message=record.error_message,
        completed_at=record.completed_at,
    )


def _investigation_to_record(
    investigation: ScientificReturnInvestigation, encryptor: FieldEncryptor
) -> ScientificReturnInvestigationRecord:
    return ScientificReturnInvestigationRecord(
        id=investigation.id,
        watch_id=investigation.watch_id,
        candidate_id=investigation.candidate_id,
        initial_run_id=investigation.initial_run_id,
        previous_investigation_id=investigation.previous_investigation_id,
        idempotency_key=investigation.idempotency_key,
        objective=investigation.objective,
        status=investigation.status,
        mode=investigation.mode,
        stop_reason=investigation.stop_reason,
        current_iteration=investigation.current_iteration,
        budget=_budget_to_json(investigation.budget),
        started_at=investigation.started_at,
        completed_at=investigation.completed_at,
        heartbeat_at=investigation.heartbeat_at,
        created_by=investigation.created_by,
        contract_version=AGENT_CONTRACT_VERSION,
        version=investigation.version,
        iterations=[
            _iteration_to_record(item, encryptor) for item in investigation.iterations
        ],
    )


def _investigation_to_domain(
    record: ScientificReturnInvestigationRecord, encryptor: FieldEncryptor
) -> ScientificReturnInvestigation:
    return ScientificReturnInvestigation(
        id=InvestigationId(record.id),
        watch_id=ScientificReturnWatchId(record.watch_id),
        objective=record.objective,
        mode=record.mode,
        initial_run_id=ScientificReturnRunId(record.initial_run_id),
        budget=_budget_to_domain(record.budget),
        created_by=PermissionId(record.created_by),
        started_at=record.started_at,
        status=record.status,
        candidate_id=(
            CandidatePublicationId(record.candidate_id) if record.candidate_id else None
        ),
        previous_investigation_id=(
            InvestigationId(record.previous_investigation_id)
            if record.previous_investigation_id
            else None
        ),
        idempotency_key=record.idempotency_key,
        current_iteration=record.current_iteration,
        stop_reason=record.stop_reason,
        completed_at=record.completed_at,
        heartbeat_at=record.heartbeat_at,
        version=record.version,
        iterations=[
            _iteration_to_domain(item, encryptor)
            for item in sorted(record.iterations, key=lambda item: item.number)
        ],
    )


def _tool_execution_to_record(
    execution: ToolExecutionRecord, encryptor: FieldEncryptor
) -> ScientificReturnToolExecutionRecord:
    return ScientificReturnToolExecutionRecord(
        id=execution.id,
        investigation_id=execution.investigation_id,
        iteration_id=execution.iteration_id,
        idempotency_key=execution.idempotency_key,
        action=execution.action,
        queries_payload=encryptor.encrypt_json(list(execution.queries), _TOOL_QUERIES),
        sources=list(execution.sources),
        total_results=execution.total_results,
        created_candidate_ids=list(execution.created_candidate_ids),
        added_evidence_ids=list(execution.added_evidence_ids),
        result_hash=execution.result_hash,
        succeeded=execution.succeeded,
        error_message=execution.error_message,
        attempts=execution.attempts,
        started_at=execution.started_at,
        completed_at=execution.completed_at,
    )


def _tool_execution_to_domain(
    record: ScientificReturnToolExecutionRecord, encryptor: FieldEncryptor
) -> ToolExecutionRecord:
    queries = encryptor.decrypt_json(record.queries_payload, _TOOL_QUERIES) or []
    return ToolExecutionRecord(
        id=ToolExecutionId(record.id),
        investigation_id=InvestigationId(record.investigation_id),
        iteration_id=record.iteration_id,
        idempotency_key=record.idempotency_key,
        action=record.action,
        started_at=record.started_at,
        queries=tuple(cast("list[str]", queries)),
        sources=tuple(record.sources or []),
        total_results=record.total_results,
        created_candidate_ids=tuple(record.created_candidate_ids or []),
        added_evidence_ids=tuple(record.added_evidence_ids or []),
        result_hash=record.result_hash,
        succeeded=record.succeeded,
        error_message=record.error_message,
        attempts=record.attempts,
        completed_at=record.completed_at,
    )


def _candidate_to_domain(record: CandidatePublicationRecord) -> CandidatePublication:
    relation_kinds = {item.relation_kind.value for item in record.agentic_links}
    return CandidatePublication(
        id=CandidatePublicationId(record.id),
        watch_id=ScientificReturnWatchId(record.watch_id),
        first_seen_run_id=ScientificReturnRunId(record.first_seen_run_id),
        source=record.source,
        source_record_id=record.source_record_id,
        deduplication_key=record.deduplication_key,
        doi=record.doi,
        title=record.title,
        authors=tuple(record.authors),
        publication_date=record.publication_date,
        abstract=record.abstract,
        url=record.url,
        raw_metadata_hash=record.raw_metadata_hash,
        status=record.status,
        confirmed_publication_entry_id=record.confirmed_publication_entry_id,
        created_at=record.created_at,
        evidences=[_evidence_to_domain(item) for item in record.evidences],
        first_seen_kind=record.first_seen_run.run_kind,
        agentic_created="CREATED" in relation_kinds,
        agentic_rediscovered="REDISCOVERED" in relation_kinds,
    )


def _decision_to_domain(
    record: CandidateDecisionRecord, encryptor: FieldEncryptor
) -> CandidateDecision:
    correction = (
        CandidateCorrection(
            title=record.correction.get("title"),
            doi=record.correction.get("doi"),
            url=record.correction.get("url"),
            authors=(
                tuple(record.correction["authors"])
                if record.correction.get("authors") is not None
                else None
            ),
        )
        if record.correction is not None
        else None
    )
    raw_context = encryptor.decrypt_json(
        record.decision_context_encrypted, _DECISION_CONTEXT
    )
    context = cast(dict[str, object] | None, raw_context)

    def context_strings(key: str) -> tuple[str, ...]:
        if context is None:
            return ()
        value = context.get(key, [])
        return tuple(str(item) for item in value) if isinstance(value, list) else ()

    def context_optional_string(key: str) -> str | None:
        if context is None or context.get(key) is None:
            return None
        return str(context[key])

    def context_grounded_forms() -> tuple[GroundedInventoryForm, ...]:
        if context is None:
            return ()
        raw_forms = context.get("grounded_inventory_forms")
        if not isinstance(raw_forms, list):
            return ()
        forms: list[GroundedInventoryForm] = []
        for item in raw_forms:
            if not isinstance(item, dict):
                continue
            try:
                forms.append(
                    GroundedInventoryForm(
                        observed_form=str(item["observed_form"]),
                        source_field=EvidenceSourceField(str(item["source_field"])),
                        source_locator=(
                            str(item["source_locator"])
                            if item.get("source_locator")
                            else None
                        ),
                    )
                )
            except (KeyError, ValueError):
                continue
        return tuple(forms)

    return CandidateDecision(
        id=CandidateDecisionId(record.id),
        candidate_id=CandidatePublicationId(record.candidate_id),
        decision=record.decision,
        justification=record.justification,
        decided_by=PermissionId(record.decided_by),
        decided_at=record.decided_at,
        evidence_snapshot=tuple(record.evidence_snapshot),
        correction=correction,
        decision_context=(
            CandidateDecisionContext(
                version=int(str(context["version"])),
                passages=context_strings("passages"),
                inventory_forms=context_strings("inventory_forms"),
                queries=context_strings("queries"),
                sources=context_strings("sources"),
                explanation=str(context["explanation"]),
                confidence=AgentConfidence(str(context["confidence"])),
                contradictions=context_strings("contradictions"),
                knowledge_item_ids=tuple(
                    KnowledgeItemId(value)
                    for value in context_strings("knowledge_item_ids")
                ),
                discovery_basis=context_optional_string("discovery_basis"),
                search_intent=context_optional_string("search_intent"),
                search_strategy=context_optional_string("search_strategy"),
                inventory_evidence_status=(
                    InventoryEvidenceStatus(str(context["inventory_evidence_status"]))
                    if context.get("inventory_evidence_status")
                    else None
                ),
                grounded_inventory_forms=context_grounded_forms(),
            )
            if context is not None
            else None
        ),
    )


def _analysis_result_to_dict(result: CandidateAnalysisResult) -> dict[str, object]:
    return {
        "summary": result.summary,
        "supporting_evidence": list(result.supporting_evidence),
        "contradictions": list(result.contradictions),
        "missing_evidence": list(result.missing_evidence),
        "recommended_action": result.recommended_action.value,
        "proposed_queries": list(result.proposed_queries),
        "reasoning_summary": result.reasoning_summary,
        "confidence": result.confidence.value,
    }


def _analysis_result_to_domain(payload: dict[str, object]) -> CandidateAnalysisResult:
    def strings(key: str) -> tuple[str, ...]:
        value = payload.get(key, [])
        return tuple(str(item) for item in value) if isinstance(value, list) else ()

    return CandidateAnalysisResult(
        summary=str(payload["summary"]),
        supporting_evidence=strings("supporting_evidence"),
        contradictions=strings("contradictions"),
        missing_evidence=strings("missing_evidence"),
        recommended_action=AgentRecommendedAction(str(payload["recommended_action"])),
        proposed_queries=strings("proposed_queries"),
        reasoning_summary=str(payload["reasoning_summary"]),
        confidence=AgentConfidence(str(payload["confidence"])),
    )


def _agent_analysis_to_domain(
    record: CandidateAgentAnalysisRecord, encryptor: FieldEncryptor
) -> CandidateAgentAnalysis:
    raw_result = encryptor.decrypt_json(record.analysis_payload, _AGENT_ANALYSIS)
    raw_input = encryptor.decrypt_json(record.input_payload, _AGENT_INPUT)
    return CandidateAgentAnalysis(
        id=CandidateAgentAnalysisId(record.id),
        candidate_id=CandidatePublicationId(record.candidate_id),
        run_id=ScientificReturnRunId(record.run_id),
        status=record.status,
        model=record.model,
        prompt_version_id=record.prompt_version_id,
        prompt_version=record.prompt_version,
        input_payload=cast(dict[str, object], raw_input),
        input_hash=record.input_hash,
        result=(
            _analysis_result_to_domain(cast(dict[str, object], raw_result))
            if raw_result is not None
            else None
        ),
        response_hash=record.response_hash,
        started_at=record.started_at,
        completed_at=record.completed_at,
        latency_ms=record.latency_ms,
        error_message=record.error_message,
        created_by=PermissionId(record.created_by),
        staff_feedback=record.staff_feedback,
        feedback_comment=record.feedback_comment,
        feedback_by=(
            PermissionId(record.feedback_by) if record.feedback_by is not None else None
        ),
        feedback_at=record.feedback_at,
    )


class SqlAlchemyScientificReturnRepository:
    def __init__(self, session: AsyncSession, encryptor: FieldEncryptor) -> None:
        self._session = session
        self._encryptor = encryptor

    async def add_watch(self, watch: ScientificReturnWatch) -> None:
        self._session.add(
            ScientificReturnWatchRecord(
                id=watch.id,
                project_id=watch.project_id,
                status=watch.status,
                review_interval_days=watch.review_interval_days,
                created_by=watch.created_by,
                created_at=watch.created_at,
                last_run_at=watch.last_run_at,
                next_run_at=watch.next_run_at,
                project_snapshot_id=watch.project_snapshot_id,
            )
        )
        await self._session.flush()

    async def save_watch(self, watch: ScientificReturnWatch) -> None:
        record = await self._session.get(ScientificReturnWatchRecord, watch.id)
        if record is None:
            raise LookupError(f"Scientific-return watch {watch.id} not found")
        record.status = watch.status
        record.review_interval_days = watch.review_interval_days
        record.last_run_at = watch.last_run_at
        record.next_run_at = watch.next_run_at
        await self._session.flush()

    async def get_watch(
        self, watch_id: ScientificReturnWatchId
    ) -> ScientificReturnWatch | None:
        record = await self._session.get(ScientificReturnWatchRecord, watch_id)
        return _watch_to_domain(record) if record is not None else None

    async def get_watch_by_project(
        self, project_id: str
    ) -> ScientificReturnWatch | None:
        result = await self._session.execute(
            select(ScientificReturnWatchRecord).where(
                ScientificReturnWatchRecord.project_id == project_id
            )
        )
        record = result.scalar_one_or_none()
        return _watch_to_domain(record) if record is not None else None

    async def list_due_watches(
        self, now: datetime, limit: int
    ) -> list[ScientificReturnWatch]:
        result = await self._session.execute(
            select(ScientificReturnWatchRecord)
            .where(
                ScientificReturnWatchRecord.status == WatchStatus.ACTIVE,
                ScientificReturnWatchRecord.next_run_at <= now,
            )
            .order_by(ScientificReturnWatchRecord.next_run_at)
            .limit(limit)
        )
        return [_watch_to_domain(item) for item in result.scalars().all()]

    async def add_snapshot(self, snapshot: ScientificReturnProjectSnapshot) -> None:
        self._session.add(
            ScientificReturnSnapshotRecord(
                id=snapshot.id,
                project_id=snapshot.project_id,
                payload=self._encryptor.encrypt_json(
                    _payload_to_dict(snapshot.payload), _SNAPSHOT_PAYLOAD
                )
                or "",
                payload_hash=snapshot.payload_hash,
                builder_version=snapshot.builder_version,
                created_at=snapshot.created_at,
            )
        )
        await self._session.flush()

    async def get_snapshot_for_watch(
        self, watch_id: ScientificReturnWatchId
    ) -> ScientificReturnProjectSnapshot | None:
        result = await self._session.execute(
            select(ScientificReturnSnapshotRecord)
            .join(
                ScientificReturnWatchRecord,
                ScientificReturnWatchRecord.project_snapshot_id
                == ScientificReturnSnapshotRecord.id,
            )
            .where(ScientificReturnWatchRecord.id == watch_id)
        )
        record = result.scalar_one_or_none()
        if record is None:
            return None
        return ScientificReturnProjectSnapshot(
            id=ScientificReturnSnapshotId(record.id),
            project_id=record.project_id,
            payload=_payload_to_domain(
                cast(
                    dict[str, object],
                    self._encryptor.decrypt_json(record.payload, _SNAPSHOT_PAYLOAD),
                )
            ),
            payload_hash=record.payload_hash,
            builder_version=record.builder_version,
            created_at=record.created_at,
        )

    async def add_run(self, run: ScientificReturnSearchRun) -> None:
        self._session.add(
            ScientificReturnRunRecord(
                id=run.id,
                watch_id=run.watch_id,
                status=run.status,
                started_at=run.started_at,
                completed_at=run.completed_at,
                source_count=run.source_count,
                candidate_count=run.candidate_count,
                new_candidate_count=run.new_candidate_count,
                error_message=run.error_message,
                run_kind=run.run_kind,
            )
        )
        await self._session.flush()

    async def save_run(self, run: ScientificReturnSearchRun) -> None:
        record = await self._session.get(ScientificReturnRunRecord, run.id)
        if record is None:
            raise LookupError(f"Scientific-return run {run.id} not found")
        record.status = run.status
        record.completed_at = run.completed_at
        record.source_count = run.source_count
        record.candidate_count = run.candidate_count
        record.new_candidate_count = run.new_candidate_count
        record.error_message = run.error_message
        await self._session.flush()

    async def get_run(
        self, run_id: ScientificReturnRunId
    ) -> ScientificReturnSearchRun | None:
        record = await self._session.get(ScientificReturnRunRecord, run_id)
        return _run_to_domain(record) if record is not None else None

    async def list_runs(
        self, watch_id: ScientificReturnWatchId, page: int, size: int
    ) -> tuple[list[ScientificReturnSearchRun], int]:
        where = ScientificReturnRunRecord.watch_id == watch_id
        total = int(
            (
                await self._session.execute(
                    select(func.count())
                    .select_from(ScientificReturnRunRecord)
                    .where(where)
                )
            ).scalar_one()
        )
        result = await self._session.execute(
            select(ScientificReturnRunRecord)
            .where(where)
            .order_by(ScientificReturnRunRecord.started_at.desc())
            .offset(page * size)
            .limit(size)
        )
        return [_run_to_domain(item) for item in result.scalars().all()], total

    async def add_query(self, query: ScientificReturnQuery) -> None:
        self._session.add(
            ScientificReturnQueryRecord(
                id=query.id,
                run_id=query.run_id,
                source=query.source,
                query_text=self._encryptor.encrypt_required_text(
                    query.query_text, _QUERY_TEXT
                ),
                query_type=query.query_type,
                sent_at=query.sent_at,
                result_count=query.result_count,
                status=query.status,
                error_message=query.error_message,
            )
        )
        await self._session.flush()

    async def list_queries(self, run_id: str) -> list[ScientificReturnQuery]:
        result = await self._session.execute(
            select(ScientificReturnQueryRecord)
            .where(ScientificReturnQueryRecord.run_id == run_id)
            .order_by(
                ScientificReturnQueryRecord.sent_at,
                ScientificReturnQueryRecord.id,
            )
        )
        return [
            _query_to_domain(item, self._encryptor) for item in result.scalars().all()
        ]

    async def get_candidate(
        self, candidate_id: CandidatePublicationId
    ) -> CandidatePublication | None:
        result = await self._session.execute(
            select(CandidatePublicationRecord)
            .where(CandidatePublicationRecord.id == candidate_id)
            .options(
                selectinload(CandidatePublicationRecord.evidences),
                selectinload(CandidatePublicationRecord.first_seen_run),
                selectinload(CandidatePublicationRecord.agentic_links),
            )
        )
        record = result.scalar_one_or_none()
        return _candidate_to_domain(record) if record is not None else None

    async def get_candidate_by_key(
        self, watch_id: ScientificReturnWatchId, key: str
    ) -> CandidatePublication | None:
        result = await self._session.execute(
            select(CandidatePublicationRecord)
            .where(
                CandidatePublicationRecord.watch_id == watch_id,
                CandidatePublicationRecord.deduplication_key == key,
            )
            .options(
                selectinload(CandidatePublicationRecord.evidences),
                selectinload(CandidatePublicationRecord.first_seen_run),
                selectinload(CandidatePublicationRecord.agentic_links),
            )
        )
        record = result.scalar_one_or_none()
        return _candidate_to_domain(record) if record is not None else None

    async def add_candidate(self, candidate: CandidatePublication) -> None:
        self._session.add(
            CandidatePublicationRecord(
                id=candidate.id,
                watch_id=candidate.watch_id,
                first_seen_run_id=candidate.first_seen_run_id,
                source=candidate.source,
                source_record_id=candidate.source_record_id,
                deduplication_key=candidate.deduplication_key,
                doi=candidate.doi,
                title=candidate.title,
                authors=list(candidate.authors),
                publication_date=candidate.publication_date,
                abstract=candidate.abstract,
                url=candidate.url,
                raw_metadata_hash=candidate.raw_metadata_hash,
                status=candidate.status,
                confirmed_publication_entry_id=candidate.confirmed_publication_entry_id,
                created_at=candidate.created_at,
                evidences=[
                    CandidateEvidenceRecord(
                        id=evidence.id,
                        candidate_id=candidate.id,
                        type=evidence.type,
                        strength=evidence.strength,
                        value=evidence.value,
                        source_field=evidence.source_field,
                        explanation=evidence.explanation,
                        created_at=evidence.created_at,
                        object_id=evidence.object_id,
                    )
                    for evidence in candidate.evidences
                ],
            )
        )
        await self._session.flush()

    async def save_candidate(self, candidate: CandidatePublication) -> None:
        record = await self._session.get(CandidatePublicationRecord, candidate.id)
        if record is None:
            raise LookupError(f"Candidate {candidate.id} not found")
        record.title = candidate.title
        record.authors = list(candidate.authors)
        record.doi = candidate.doi
        record.url = candidate.url
        record.status = candidate.status
        record.confirmed_publication_entry_id = candidate.confirmed_publication_entry_id
        await self._session.flush()

    async def list_candidates(
        self,
        project_id: str,
        status: CandidateStatus | None,
        page: int,
        size: int,
    ) -> tuple[list[CandidatePublication], int]:
        filters = [ScientificReturnWatchRecord.project_id == project_id]
        if status is not None:
            filters.append(CandidatePublicationRecord.status == status)
        total = int(
            (
                await self._session.execute(
                    select(func.count())
                    .select_from(CandidatePublicationRecord)
                    .join(
                        ScientificReturnWatchRecord,
                        CandidatePublicationRecord.watch_id
                        == ScientificReturnWatchRecord.id,
                    )
                    .where(*filters)
                )
            ).scalar_one()
        )
        result = await self._session.execute(
            select(CandidatePublicationRecord)
            .join(
                ScientificReturnWatchRecord,
                CandidatePublicationRecord.watch_id == ScientificReturnWatchRecord.id,
            )
            .where(*filters)
            .options(
                selectinload(CandidatePublicationRecord.evidences),
                selectinload(CandidatePublicationRecord.first_seen_run),
                selectinload(CandidatePublicationRecord.agentic_links),
            )
            .order_by(
                CandidatePublicationRecord.created_at.desc(),
                CandidatePublicationRecord.id.desc(),
            )
            .offset(page * size)
            .limit(size)
        )
        return [_candidate_to_domain(item) for item in result.scalars().all()], total

    async def add_decision(self, decision: CandidateDecision) -> None:
        self._session.add(
            CandidateDecisionRecord(
                id=decision.id,
                candidate_id=decision.candidate_id,
                decision=decision.decision,
                justification=decision.justification,
                decided_by=decision.decided_by,
                decided_at=decision.decided_at,
                evidence_snapshot=list(decision.evidence_snapshot),
                correction=(
                    asdict(decision.correction) if decision.correction else None
                ),
                decision_context_encrypted=self._encryptor.encrypt_json(
                    (
                        asdict(decision.decision_context)
                        if decision.decision_context is not None
                        else None
                    ),
                    _DECISION_CONTEXT,
                ),
            )
        )
        await self._session.flush()

    async def list_candidate_queue(
        self,
        status: CandidateStatus | None,
        project_id: str | None,
        source: str | None,
        evidence_strength: EvidenceStrength | None,
        page: int,
        size: int,
    ) -> tuple[list[CandidateReviewItem], int]:
        filters: list[ColumnElement[bool]] = []
        if status is not None:
            filters.append(CandidatePublicationRecord.status == status)
        if project_id:
            filters.append(ScientificReturnWatchRecord.project_id == project_id)
        if source:
            filters.append(CandidatePublicationRecord.source == source)
        if evidence_strength is not None:
            filters.append(
                exists().where(
                    CandidateEvidenceRecord.candidate_id
                    == CandidatePublicationRecord.id,
                    CandidateEvidenceRecord.strength == evidence_strength,
                )
            )

        joined = (
            select(CandidatePublicationRecord, ScientificReturnWatchRecord.project_id)
            .join(
                ScientificReturnWatchRecord,
                CandidatePublicationRecord.watch_id == ScientificReturnWatchRecord.id,
            )
            .where(*filters)
        )
        total = int(
            (
                await self._session.execute(
                    select(func.count()).select_from(
                        joined.with_only_columns(
                            CandidatePublicationRecord.id
                        ).subquery()
                    )
                )
            ).scalar_one()
        )
        result = await self._session.execute(
            joined.options(
                selectinload(CandidatePublicationRecord.evidences),
                selectinload(CandidatePublicationRecord.first_seen_run),
                selectinload(CandidatePublicationRecord.agentic_links),
            )
            .order_by(
                CandidatePublicationRecord.created_at.desc(),
                CandidatePublicationRecord.id.desc(),
            )
            .offset(page * size)
            .limit(size)
        )
        rows = result.all()
        candidate_ids = [candidate.id for candidate, _ in rows]
        latest_payloads: dict[str, dict[str, object]] = {}
        if candidate_ids:
            analysis_result = await self._session.execute(
                select(CandidateAgentAnalysisRecord)
                .where(
                    CandidateAgentAnalysisRecord.candidate_id.in_(candidate_ids),
                    CandidateAgentAnalysisRecord.prompt_version_id.like(
                        f"{FULL_AGENTIC_READER_PROMPT_ID_PREFIX}%"
                    ),
                    CandidateAgentAnalysisRecord.status
                    == AgentAnalysisStatus.COMPLETED,
                )
                .order_by(
                    CandidateAgentAnalysisRecord.candidate_id,
                    CandidateAgentAnalysisRecord.started_at.desc(),
                    CandidateAgentAnalysisRecord.id.desc(),
                )
            )
            for record in analysis_result.scalars():
                if record.candidate_id in latest_payloads:
                    continue
                payload = self._encryptor.decrypt_json(
                    record.input_payload, _AGENT_INPUT
                )
                if isinstance(payload, dict):
                    latest_payloads[record.candidate_id] = cast(
                        dict[str, object], payload
                    )

        def optional_string(payload: dict[str, object], key: str) -> str | None:
            value = payload.get(key)
            return str(value) if value is not None else None

        def grounded_forms(
            payload: dict[str, object],
        ) -> tuple[dict[str, str | None], ...]:
            value = payload.get("groundedInventoryForms")
            if not isinstance(value, list):
                return ()
            forms: list[dict[str, str | None]] = []
            for item in value:
                if not isinstance(item, dict):
                    continue
                observed = optional_string(item, "observedForm")
                source_field = optional_string(item, "sourceField")
                if observed is None or source_field is None:
                    continue
                forms.append(
                    {
                        "observedForm": observed,
                        "sourceField": source_field,
                        "sourceLocator": optional_string(item, "sourceLocator"),
                    }
                )
            return tuple(forms)

        def grounded_passages(payload: dict[str, object]) -> tuple[str, ...]:
            value = payload.get("passages")
            if not isinstance(value, list):
                return ()
            return tuple(item for item in value if isinstance(item, str) and item)

        def nonnegative_int(payload: dict[str, object], key: str) -> int:
            value = payload.get(key)
            return value if isinstance(value, int) and value >= 0 else 0

        return (
            [
                CandidateReviewItem(
                    project_id=project_id_value,
                    candidate=_candidate_to_domain(candidate),
                    discovery_basis=optional_string(
                        latest_payloads.get(candidate.id, {}), "discoveryBasis"
                    ),
                    search_intent=optional_string(
                        latest_payloads.get(candidate.id, {}), "searchIntent"
                    ),
                    search_strategy=optional_string(
                        latest_payloads.get(candidate.id, {}), "searchStrategy"
                    ),
                    inventory_evidence_status=optional_string(
                        latest_payloads.get(candidate.id, {}),
                        "inventoryEvidenceStatus",
                    ),
                    grounded_inventory_forms=grounded_forms(
                        latest_payloads.get(candidate.id, {})
                    ),
                    grounded_passages=grounded_passages(
                        latest_payloads.get(candidate.id, {})
                    ),
                    rejected_passage_count=nonnegative_int(
                        latest_payloads.get(candidate.id, {}),
                        "rejectedPassageCount",
                    ),
                    rejected_inventory_form_count=nonnegative_int(
                        latest_payloads.get(candidate.id, {}),
                        "rejectedInventoryFormCount",
                    ),
                )
                for candidate, project_id_value in rows
            ],
            total,
        )

    async def list_decisions(
        self, candidate_id: CandidatePublicationId
    ) -> list[CandidateDecision]:
        result = await self._session.execute(
            select(CandidateDecisionRecord)
            .where(CandidateDecisionRecord.candidate_id == candidate_id)
            .order_by(CandidateDecisionRecord.decided_at, CandidateDecisionRecord.id)
        )
        return [
            _decision_to_domain(item, self._encryptor)
            for item in result.scalars().all()
        ]

    async def get_metrics(self) -> ScientificReturnMetrics:
        async def count(model: type[Any], *filters: ColumnElement[bool]) -> int:
            statement = select(func.count()).select_from(model)
            if filters:
                statement = statement.where(*filters)
            return int((await self._session.execute(statement)).scalar_one())

        async def count_candidates_for_run_kind(
            run_kind: RunKind, status: CandidateStatus
        ) -> int:
            statement = (
                select(func.count(func.distinct(CandidatePublicationRecord.id)))
                .select_from(CandidatePublicationRecord)
                .join(
                    ScientificReturnRunRecord,
                    CandidatePublicationRecord.first_seen_run_id
                    == ScientificReturnRunRecord.id,
                )
                .where(
                    ScientificReturnRunRecord.run_kind == run_kind,
                    CandidatePublicationRecord.status == status,
                )
            )
            return int((await self._session.execute(statement)).scalar_one())

        async def count_agentic_linked(status: CandidateStatus) -> int:
            statement = (
                select(func.count(func.distinct(CandidatePublicationRecord.id)))
                .select_from(CandidatePublicationRecord)
                .join(
                    AgenticInvestigationCandidateRecord,
                    AgenticInvestigationCandidateRecord.candidate_id
                    == CandidatePublicationRecord.id,
                )
                .where(CandidatePublicationRecord.status == status)
            )
            return int((await self._session.execute(statement)).scalar_one())

        return ScientificReturnMetrics(
            active_watches=await count(
                ScientificReturnWatchRecord,
                ScientificReturnWatchRecord.status == WatchStatus.ACTIVE,
            ),
            runs=await count(
                ScientificReturnRunRecord,
                ScientificReturnRunRecord.run_kind == RunKind.DETERMINISTIC,
            ),
            failed_runs=await count(
                ScientificReturnRunRecord,
                ScientificReturnRunRecord.status == RunStatus.FAILED,
                ScientificReturnRunRecord.run_kind == RunKind.DETERMINISTIC,
            ),
            pending_candidates=await count_candidates_for_run_kind(
                RunKind.DETERMINISTIC, CandidateStatus.PENDING
            ),
            confirmed_candidates=await count_candidates_for_run_kind(
                RunKind.DETERMINISTIC, CandidateStatus.CONFIRMED
            ),
            dismissed_candidates=await count_candidates_for_run_kind(
                RunKind.DETERMINISTIC, CandidateStatus.DISMISSED
            ),
            full_agentic_runs=await count(
                ScientificReturnRunRecord,
                ScientificReturnRunRecord.run_kind == RunKind.FULL_AGENTIC,
            ),
            full_agentic_failed_runs=await count(
                ScientificReturnRunRecord,
                ScientificReturnRunRecord.run_kind == RunKind.FULL_AGENTIC,
                ScientificReturnRunRecord.status == RunStatus.FAILED,
            ),
            full_agentic_pending_candidates=await count_agentic_linked(
                CandidateStatus.PENDING
            ),
            full_agentic_confirmed_candidates=await count_agentic_linked(
                CandidateStatus.CONFIRMED
            ),
            full_agentic_dismissed_candidates=await count_agentic_linked(
                CandidateStatus.DISMISSED
            ),
        )

    async def add_agent_analysis(self, analysis: CandidateAgentAnalysis) -> None:
        self._session.add(
            CandidateAgentAnalysisRecord(
                id=analysis.id,
                candidate_id=analysis.candidate_id,
                run_id=analysis.run_id,
                status=analysis.status,
                model=analysis.model,
                prompt_version_id=analysis.prompt_version_id,
                prompt_version=analysis.prompt_version,
                input_payload=self._encryptor.encrypt_json(
                    analysis.input_payload, _AGENT_INPUT
                )
                or "",
                input_hash=analysis.input_hash,
                analysis_payload=(
                    self._encryptor.encrypt_json(
                        _analysis_result_to_dict(analysis.result), _AGENT_ANALYSIS
                    )
                    if analysis.result is not None
                    else None
                ),
                recommended_action=(
                    analysis.result.recommended_action if analysis.result else None
                ),
                confidence=analysis.result.confidence if analysis.result else None,
                response_hash=analysis.response_hash,
                started_at=analysis.started_at,
                completed_at=analysis.completed_at,
                latency_ms=analysis.latency_ms,
                error_message=analysis.error_message,
                created_by=analysis.created_by,
                staff_feedback=analysis.staff_feedback,
                feedback_comment=analysis.feedback_comment,
                feedback_by=analysis.feedback_by,
                feedback_at=analysis.feedback_at,
            )
        )
        await self._session.flush()

    async def save_agent_analysis(self, analysis: CandidateAgentAnalysis) -> None:
        record = await self._session.get(CandidateAgentAnalysisRecord, analysis.id)
        if record is None:
            raise LookupError(f"Agent analysis {analysis.id} not found")
        record.status = analysis.status
        record.analysis_payload = (
            self._encryptor.encrypt_json(
                _analysis_result_to_dict(analysis.result), _AGENT_ANALYSIS
            )
            if analysis.result is not None
            else None
        )
        record.recommended_action = (
            analysis.result.recommended_action if analysis.result else None
        )
        record.confidence = analysis.result.confidence if analysis.result else None
        record.response_hash = analysis.response_hash
        record.completed_at = analysis.completed_at
        record.latency_ms = analysis.latency_ms
        record.error_message = analysis.error_message
        record.staff_feedback = analysis.staff_feedback
        record.feedback_comment = analysis.feedback_comment
        record.feedback_by = analysis.feedback_by
        record.feedback_at = analysis.feedback_at
        await self._session.flush()

    async def get_agent_analysis(
        self, analysis_id: CandidateAgentAnalysisId
    ) -> CandidateAgentAnalysis | None:
        record = await self._session.get(CandidateAgentAnalysisRecord, analysis_id)
        return (
            _agent_analysis_to_domain(record, self._encryptor)
            if record is not None
            else None
        )

    async def list_agent_analyses(
        self, candidate_id: CandidatePublicationId
    ) -> list[CandidateAgentAnalysis]:
        result = await self._session.execute(
            select(CandidateAgentAnalysisRecord)
            .where(CandidateAgentAnalysisRecord.candidate_id == candidate_id)
            .order_by(
                CandidateAgentAnalysisRecord.started_at.desc(),
                CandidateAgentAnalysisRecord.id.desc(),
            )
        )
        return [
            _agent_analysis_to_domain(item, self._encryptor)
            for item in result.scalars().all()
        ]

    async def list_queries_for_watch(
        self, watch_id: ScientificReturnWatchId
    ) -> list[ScientificReturnQuery]:
        result = await self._session.execute(
            select(ScientificReturnQueryRecord)
            .join(
                ScientificReturnRunRecord,
                ScientificReturnRunRecord.id == ScientificReturnQueryRecord.run_id,
            )
            .where(ScientificReturnRunRecord.watch_id == watch_id)
            .order_by(
                ScientificReturnQueryRecord.sent_at,
                ScientificReturnQueryRecord.id,
            )
        )
        return [
            _query_to_domain(item, self._encryptor) for item in result.scalars().all()
        ]

    async def append_candidate_evidences(
        self,
        candidate_id: CandidatePublicationId,
        evidences: tuple[CandidateEvidence, ...],
    ) -> tuple[CandidateEvidence, ...]:
        if not evidences:
            return ()
        existing = await self._session.execute(
            select(CandidateEvidenceRecord).where(
                CandidateEvidenceRecord.candidate_id == candidate_id
            )
        )
        # Identity ignores the row id and the timestamp, so re-running the same
        # tool over the same records adds nothing and the original provenance is
        # never overwritten.
        known = {
            _evidence_identity(_evidence_to_domain(item))
            for item in existing.scalars().all()
        }
        written: list[CandidateEvidence] = []
        for evidence in evidences:
            if _evidence_identity(evidence) in known:
                continue
            known.add(_evidence_identity(evidence))
            self._session.add(
                CandidateEvidenceRecord(
                    id=evidence.id,
                    candidate_id=candidate_id,
                    type=evidence.type,
                    strength=evidence.strength,
                    value=evidence.value,
                    source_field=evidence.source_field,
                    explanation=evidence.explanation,
                    created_at=evidence.created_at,
                    object_id=evidence.object_id,
                    investigation_id=evidence.investigation_id,
                    iteration_id=evidence.iteration_id,
                    tool_execution_id=evidence.tool_execution_id,
                    query_id=evidence.query_id,
                    source_record_id=evidence.source_record_id,
                    content_hash=evidence.content_hash,
                )
            )
            written.append(evidence)
        await self._session.flush()
        return tuple(written)


class SqlAlchemyInvestigationRepository:
    """Persists the investigation aggregate, its iterations and tool executions.

    Observations, plans and reflections carry project data and model output, so
    they are encrypted at rest exactly like the snapshot payload and the query
    text of the deterministic pipeline.
    """

    def __init__(self, session: AsyncSession, encryptor: FieldEncryptor) -> None:
        self._session = session
        self._encryptor = encryptor

    async def add(self, investigation: ScientificReturnInvestigation) -> None:
        self._session.add(_investigation_to_record(investigation, self._encryptor))
        await self._session.flush()

    async def save(self, investigation: ScientificReturnInvestigation) -> None:
        # The iterations are loaded eagerly because they are read a few lines
        # below. Under asyncio a lazy load there raises MissingGreenlet rather
        # than quietly issuing a query, so it has to be asked for up front.
        record = await self._session.get(
            ScientificReturnInvestigationRecord,
            investigation.id,
            options=[selectinload(ScientificReturnInvestigationRecord.iterations)],
        )
        if record is None:
            raise LookupError(f"Investigation {investigation.id} not found")
        record.status = investigation.status
        record.stop_reason = investigation.stop_reason
        record.current_iteration = investigation.current_iteration
        record.budget = _budget_to_json(investigation.budget)
        record.completed_at = investigation.completed_at
        record.heartbeat_at = investigation.heartbeat_at
        record.version = investigation.version
        stored = {item.id: item for item in record.iterations}
        for iteration in investigation.iterations:
            mapped = _iteration_to_record(iteration, self._encryptor)
            current = stored.get(iteration.id)
            if current is None:
                record.iterations.append(mapped)
                continue
            for column in (
                "status",
                "observation_payload",
                "plan_payload",
                "reflection_payload",
                "policy_authorized",
                "policy_rejection_reason",
                "policy_justification",
                "progress",
                "tool_execution_id",
                "evidence_before_hash",
                "evidence_after_hash",
                "evidence_delta",
                "model",
                "prompt_version",
                "plan_latency_ms",
                "reflection_latency_ms",
                "plan_response_hash",
                "reflection_response_hash",
                "error_message",
                "completed_at",
            ):
                setattr(current, column, getattr(mapped, column))
        await self._session.flush()

    async def get(
        self, investigation_id: InvestigationId
    ) -> ScientificReturnInvestigation | None:
        result = await self._session.execute(
            select(ScientificReturnInvestigationRecord)
            .where(ScientificReturnInvestigationRecord.id == investigation_id)
            .options(selectinload(ScientificReturnInvestigationRecord.iterations))
        )
        record = result.scalar_one_or_none()
        if record is None:
            return None
        investigation = _investigation_to_domain(record, self._encryptor)
        await self._attach_tool_results([investigation])
        return investigation

    async def _attach_tool_results(
        self, investigations: list[ScientificReturnInvestigation]
    ) -> None:
        """Rebuild each iteration's tool result from its execution row.

        The iteration table stores only a pointer to the execution; the outcome
        itself lives on the execution row, which is what makes a retry safe. A
        trajectory read back without this step would report that the cycle
        planned a search and never say what it searched for.
        """
        wanted = {
            str(iteration.tool_execution_id): iteration
            for investigation in investigations
            for iteration in investigation.iterations
            if iteration.tool_execution_id is not None
        }
        if not wanted:
            return
        result = await self._session.execute(
            select(ScientificReturnToolExecutionRecord).where(
                ScientificReturnToolExecutionRecord.id.in_(wanted)
            )
        )
        for record in result.scalars().all():
            execution = _tool_execution_to_domain(record, self._encryptor)
            wanted[str(execution.id)].tool_result = ToolResultSummary(
                executed_queries=execution.queries,
                sources=execution.sources,
                total_results=execution.total_results,
                created_candidate_ids=execution.created_candidate_ids,
                added_evidence_ids=execution.added_evidence_ids,
                result_hash=execution.result_hash or "",
            )

    async def list_for_watch(
        self, watch_id: ScientificReturnWatchId
    ) -> list[ScientificReturnInvestigation]:
        return await self._list(
            ScientificReturnInvestigationRecord.watch_id == watch_id
        )

    async def list_for_candidate(
        self, candidate_id: CandidatePublicationId
    ) -> list[ScientificReturnInvestigation]:
        return await self._list(
            ScientificReturnInvestigationRecord.candidate_id == candidate_id
        )

    async def find_live(
        self,
        watch_id: ScientificReturnWatchId,
        objective: InvestigationObjective,
        candidate_id: CandidatePublicationId | None,
    ) -> ScientificReturnInvestigation | None:
        filters: list[ColumnElement[bool]] = [
            ScientificReturnInvestigationRecord.watch_id == watch_id,
            ScientificReturnInvestigationRecord.objective == objective,
            ScientificReturnInvestigationRecord.status.notin_(_TERMINAL_STATUSES),
        ]
        filters.append(
            ScientificReturnInvestigationRecord.candidate_id.is_(None)
            if candidate_id is None
            else ScientificReturnInvestigationRecord.candidate_id == candidate_id
        )
        found = await self._list(*filters)
        return found[0] if found else None

    async def find_by_idempotency_key(
        self, key: str
    ) -> ScientificReturnInvestigation | None:
        found = await self._list(
            ScientificReturnInvestigationRecord.idempotency_key == key
        )
        return found[0] if found else None

    async def find_tool_execution(
        self, idempotency_key: str
    ) -> ToolExecutionRecord | None:
        result = await self._session.execute(
            select(ScientificReturnToolExecutionRecord).where(
                ScientificReturnToolExecutionRecord.idempotency_key == idempotency_key
            )
        )
        record = result.scalar_one_or_none()
        return (
            _tool_execution_to_domain(record, self._encryptor)
            if record is not None
            else None
        )

    async def add_tool_execution(self, execution: ToolExecutionRecord) -> None:
        self._session.add(_tool_execution_to_record(execution, self._encryptor))
        await self._session.flush()

    async def save_tool_execution(self, execution: ToolExecutionRecord) -> None:
        record = await self._session.get(
            ScientificReturnToolExecutionRecord, execution.id
        )
        if record is None:
            raise LookupError(f"Tool execution {execution.id} not found")
        record.queries_payload = self._encryptor.encrypt_json(
            list(execution.queries), _TOOL_QUERIES
        )
        record.sources = list(execution.sources)
        record.total_results = execution.total_results
        record.created_candidate_ids = list(execution.created_candidate_ids)
        record.added_evidence_ids = list(execution.added_evidence_ids)
        record.result_hash = execution.result_hash
        record.succeeded = execution.succeeded
        record.error_message = execution.error_message
        record.attempts = execution.attempts
        record.completed_at = execution.completed_at
        await self._session.flush()

    async def _list(
        self, *filters: ColumnElement[bool]
    ) -> list[ScientificReturnInvestigation]:
        result = await self._session.execute(
            select(ScientificReturnInvestigationRecord)
            .where(*filters)
            .options(selectinload(ScientificReturnInvestigationRecord.iterations))
            .order_by(
                ScientificReturnInvestigationRecord.started_at.desc(),
                ScientificReturnInvestigationRecord.id.desc(),
            )
        )
        investigations = [
            _investigation_to_domain(item, self._encryptor)
            for item in result.scalars().all()
        ]
        await self._attach_tool_results(investigations)
        return investigations
