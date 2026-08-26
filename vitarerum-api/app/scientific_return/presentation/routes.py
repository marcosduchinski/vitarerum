from __future__ import annotations

import logging
import secrets
from collections.abc import Mapping, Sequence
from math import ceil
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException, Query, status

from app.identity.public import Actor
from app.notifications.public import NotificationKind, RelatedResourceType
from app.scientific_return.application.agent_analysis import (
    AgentAnalysisNotFound,
    ListCandidateAgentAnalyses,
    RecordAgentAnalysisFeedback,
    RecordAgentAnalysisFeedbackInput,
)
from app.scientific_return.application.full_agentic import (
    CancelFullAgenticInvestigation,
    ExecuteFullAgenticInput,
    FullAgenticAlreadyRunning,
    FullAgenticCircuitOpen,
    FullAgenticDisabled,
    FullAgenticSourceConfigurationInvalid,
    GetFullAgenticInvestigation,
    StartFullAgenticInput,
)
from app.scientific_return.application.knowledge import (
    ActivateCuratorialKnowledge,
    CreateCuratorialKnowledge,
    CreateKnowledgeInput,
    ListCuratorialKnowledge,
    ProposeKnowledgeFromDecision,
    ReplaceCuratorialKnowledge,
    ReplaceKnowledgeInput,
    RetireCuratorialKnowledge,
)
from app.scientific_return.application.run_investigation import (
    InvestigationAlreadyRunning,
    InvestigationDisabled,
    InvestigationNotPossible,
    RunInvestigationInput,
    RunScientificReturnInvestigation,
)
from app.scientific_return.application.use_cases import (
    ActivateScientificReturnWatch,
    ActivateWatchInput,
    CandidateNotFound,
    ChangeWatchReviewInterval,
    ChangeWatchStatus,
    DecideCandidate,
    DecideCandidateInput,
    RunScientificReturnSearch,
    WatchNotFound,
)
from app.scientific_return.domain.enums import (
    CandidateStatus,
    EvidenceStrength,
    FullAgenticInvestigationStatus,
    InventoryEvidenceStatus,
    InvestigationObjective,
)
from app.scientific_return.domain.full_agentic_models import (
    FullAgenticInvestigation,
    FullAgenticInvestigationId,
    GroundedInventoryForm,
    KnowledgeItemId,
    ScientificReturnKnowledgeItem,
)
from app.scientific_return.domain.investigation_models import (
    InvestigationId,
    InvestigationIteration,
    ScientificReturnInvestigation,
)
from app.scientific_return.domain.models import (
    CandidateAgentAnalysis,
    CandidateAgentAnalysisId,
    CandidateCorrection,
    CandidateDecision,
    CandidatePublication,
    CandidatePublicationId,
    ScientificReturnSearchRun,
    ScientificReturnWatch,
    ScientificReturnWatchId,
)
from app.scientific_return.infrastructure.unit_of_work import (
    SqlAlchemyInvestigationUnitOfWork,
    SystemClock,
)
from app.scientific_return.presentation.dependencies import (
    BibliographicSources,
    DBSession,
    FullAgenticConfigDep,
    FullAgenticExecutor,
    FullAgenticReasonerDep,
    FullAgenticRepositoryDep,
    FullAgenticStarter,
    InvestigationRepository,
    InvestigationRunner,
    MaxQueries,
    Notifications,
    ProjectProvider,
    PublicationWriter,
    Repository,
    ResultLimit,
)
from app.scientific_return.presentation.schemas import (
    ActivateWatchRequest,
    AgentAnalysisFeedbackRequest,
    AgenticTrajectoryEventResponse,
    CandidateAgentAnalysisResponse,
    CandidateAgentAnalysisResultResponse,
    CandidateCorrectionRequest,
    CandidateDecisionContextResponse,
    CandidateDecisionRequest,
    CandidateDecisionResponse,
    CandidateEvidenceResponse,
    CandidatePublicationResponse,
    CandidateReviewItemResponse,
    CreateKnowledgeRequest,
    ExecuteFullAgenticRequest,
    FullAgenticInvestigationResponse,
    FullAgenticMetricsResponse,
    FullAgenticReadinessResponse,
    GroundedInventoryFormResponse,
    InvestigationBudgetResponse,
    InvestigationDeltaResponse,
    InvestigationIterationResponse,
    InvestigationObservationResponse,
    InvestigationPlanResponse,
    InvestigationPolicyResponse,
    InvestigationReflectionResponse,
    InvestigationResponse,
    InvestigationTelemetryResponse,
    InvestigationToolResponse,
    KnowledgeItemResponse,
    PaginatedCandidateQueueResponse,
    PaginatedCandidatesResponse,
    PaginatedRunsResponse,
    ProposeKnowledgeRequest,
    ReplaceKnowledgeRequest,
    ScientificReturnMetricsResponse,
    ScientificReturnQueryResponse,
    ScientificReturnRunResponse,
    ScientificReturnWatchResponse,
    StartFullAgenticRequest,
    UpdateWatchRequest,
)
from app.shared.authorization import require_staff
from app.shared.dependencies import CallerPermission

scientific_return_router = APIRouter(
    prefix="/scientific-return", tags=["scientific-return"]
)
logger = logging.getLogger(__name__)


def _full_agentic_response(
    item: FullAgenticInvestigation,
) -> FullAgenticInvestigationResponse:
    return FullAgenticInvestigationResponse(
        id=item.id,
        watchId=item.watch_id,
        objective=item.objective,
        candidateId=item.candidate_id,
        searchRunId=item.search_run_id,
        status=item.status,
        budget={
            "maxIterations": item.budget.max_iterations,
            "maxQueries": item.budget.max_queries,
            "maxResults": item.budget.max_results,
            "maxCandidates": item.budget.max_candidates,
            "maxLlmCalls": item.budget.max_llm_calls,
        },
        usage={
            "iterations": item.usage.iterations,
            "queries": item.usage.queries,
            "results": item.usage.results,
            "candidates": item.usage.candidates,
            "llmCalls": item.usage.llm_calls,
        },
        createdBy=item.created_by,
        createdAt=item.created_at,
        startedAt=item.started_at,
        completedAt=item.completed_at,
        heartbeatAt=item.heartbeat_at,
        failureReason=item.failure_reason,
        degradedReason=item.degraded_reason,
    )


@scientific_return_router.get(
    "/full-agentic-readiness", response_model=FullAgenticReadinessResponse
)
async def get_full_agentic_readiness(
    caller: CallerPermission, configuration: FullAgenticConfigDep
) -> FullAgenticReadinessResponse:
    """Report which requested sources are operational, without credentials."""
    require_staff(caller)
    return FullAgenticReadinessResponse(**configuration.source_diagnostics())


@scientific_return_router.post(
    "/watches/{watch_id}/full-agentic-investigations",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=FullAgenticInvestigationResponse,
)
async def start_full_agentic_investigation(
    watch_id: str,
    body: StartFullAgenticRequest,
    caller: CallerPermission,
    starter: FullAgenticStarter,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
) -> FullAgenticInvestigationResponse:
    try:
        item = await starter.execute(
            StartFullAgenticInput(
                watch_id=ScientificReturnWatchId(watch_id),
                objective=body.objective,
                candidate_id=(
                    CandidatePublicationId(body.candidateId)
                    if body.candidateId
                    else None
                ),
                idempotency_key=idempotency_key,
                caller=caller,
            )
        )
    except FullAgenticDisabled as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "FULL_AGENTIC_DISABLED", "message": str(exc)},
        ) from None
    except FullAgenticAlreadyRunning as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "FULL_AGENTIC_ALREADY_RUNNING", "message": str(exc)},
        ) from None
    except FullAgenticCircuitOpen as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "FULL_AGENTIC_CIRCUIT_OPEN",
                "message": str(exc),
            },
        ) from None
    except FullAgenticSourceConfigurationInvalid as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "FULL_AGENTIC_SOURCE_CONFIGURATION_INVALID",
                "message": str(exc),
            },
        ) from None
    except LookupError as exc:
        raise _not_found("SCIENTIFIC_RETURN_WATCH_NOT_FOUND", str(exc)) from None
    except ValueError as exc:
        raise _unprocessable(str(exc)) from None
    return _full_agentic_response(item)


@scientific_return_router.get(
    "/full-agentic-investigations/{investigation_id}",
    response_model=FullAgenticInvestigationResponse,
)
async def get_full_agentic_investigation(
    investigation_id: str,
    caller: CallerPermission,
    repository: FullAgenticRepositoryDep,
) -> FullAgenticInvestigationResponse:
    try:
        item = await GetFullAgenticInvestigation(repository).execute(
            FullAgenticInvestigationId(investigation_id), caller
        )
    except LookupError as exc:
        raise _not_found("FULL_AGENTIC_INVESTIGATION_NOT_FOUND", str(exc)) from None
    return _full_agentic_response(item)


@scientific_return_router.get(
    "/watches/{watch_id}/full-agentic-investigations",
    response_model=list[FullAgenticInvestigationResponse],
)
async def list_full_agentic_investigations(
    watch_id: str,
    caller: CallerPermission,
    repository: FullAgenticRepositoryDep,
    limit: int = Query(default=20, ge=1, le=100),
) -> list[FullAgenticInvestigationResponse]:
    require_staff(caller)
    items = await repository.list_investigations(watch_id, limit)
    return [_full_agentic_response(item) for item in items]


@scientific_return_router.get(
    "/full-agentic-investigations/{investigation_id}/trajectory",
    response_model=list[AgenticTrajectoryEventResponse],
)
async def get_full_agentic_trajectory(
    investigation_id: str,
    caller: CallerPermission,
    repository: FullAgenticRepositoryDep,
) -> list[AgenticTrajectoryEventResponse]:
    require_staff(caller)
    events = await repository.list_events(FullAgenticInvestigationId(investigation_id))
    return [
        AgenticTrajectoryEventResponse(
            id=event.id,
            sequence=event.sequence,
            kind=event.kind,
            payload=event.payload,
            occurredAt=event.occurred_at,
        )
        for event in events
    ]


@scientific_return_router.post(
    "/full-agentic-investigations/{investigation_id}/cancel",
    response_model=FullAgenticInvestigationResponse,
)
async def cancel_full_agentic_investigation(
    investigation_id: str,
    caller: CallerPermission,
    repository: FullAgenticRepositoryDep,
    session: DBSession,
) -> FullAgenticInvestigationResponse:
    try:
        item = await CancelFullAgenticInvestigation(
            repository,
            SqlAlchemyInvestigationUnitOfWork(session),
            SystemClock(),
        ).execute(FullAgenticInvestigationId(investigation_id), caller)
    except LookupError as exc:
        raise _not_found("FULL_AGENTIC_INVESTIGATION_NOT_FOUND", str(exc)) from None
    except ValueError as exc:
        raise _unprocessable(str(exc)) from None
    return _full_agentic_response(item)


@scientific_return_router.post(
    "/internal/full-agentic/execute",
    response_model=FullAgenticInvestigationResponse,
    include_in_schema=False,
)
async def execute_full_agentic_worker(
    body: ExecuteFullAgenticRequest,
    executor: FullAgenticExecutor,
    repository: Repository,
    full_repository: FullAgenticRepositoryDep,
    notifications: Notifications,
    session: DBSession,
    worker_token: Annotated[str, Header(alias="X-Worker-Token")],
) -> FullAgenticInvestigationResponse:
    from app.config import settings

    configured = settings.scientific_return_full_agentic_worker_token
    if not configured or not secrets.compare_digest(worker_token, configured):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    investigation_id = FullAgenticInvestigationId(body.investigationId)
    before = await full_repository.get_investigation(investigation_id)
    try:
        item = await executor.execute(
            ExecuteFullAgenticInput(
                investigation_id=investigation_id,
                worker_id=f"http-worker:{uuid4()}",
            )
        )
    except LookupError as exc:
        raise _not_found("FULL_AGENTIC_INVESTIGATION_NOT_FOUND", str(exc)) from None
    if (
        before is not None
        and not before.status.is_terminal
        and item.status is FullAgenticInvestigationStatus.COMPLETED
        and item.search_run_id is not None
    ):
        run = await repository.get_run(item.search_run_id)
        watch = await repository.get_watch(item.watch_id)
        if run and watch and run.new_candidate_count:
            try:
                await notifications.notify(
                    recipient_permission_id=watch.created_by,
                    kind=NotificationKind.SCIENTIFIC_RETURN_CANDIDATES_FOUND,
                    triggered_by=None,
                    related_resource_type=RelatedResourceType.PROJECT,
                    related_resource_id=watch.project_id,
                    note=(
                        "Autonomous scientific-return search found "
                        f"{run.new_candidate_count} new candidate(s) for review."
                    ),
                )
                await session.commit()
            except Exception:
                await session.rollback()
                logger.exception(
                    "Could not notify full-agentic investigation %s.", item.id
                )
    return _full_agentic_response(item)


def _knowledge_response(item: ScientificReturnKnowledgeItem) -> KnowledgeItemResponse:
    return KnowledgeItemResponse(
        id=item.id,
        institutionId=item.institution_id,
        kind=item.kind,
        status=item.status,
        content=item.content,
        registeredNumber=item.registered_number,
        observedForm=item.observed_form,
        supersedesId=item.supersedes_id,
        sourceCandidateId=item.source_candidate_id,
        sourceDecisionId=item.source_decision_id,
        createdBy=item.created_by,
        createdAt=item.created_at,
        validatedBy=item.validated_by,
        validatedAt=item.validated_at,
        retiredBy=item.retired_by,
        retiredAt=item.retired_at,
    )


@scientific_return_router.post(
    "/knowledge-items",
    status_code=status.HTTP_201_CREATED,
    response_model=KnowledgeItemResponse,
)
async def create_knowledge_item(
    body: CreateKnowledgeRequest,
    caller: CallerPermission,
    repository: FullAgenticRepositoryDep,
    session: DBSession,
) -> KnowledgeItemResponse:
    try:
        item = await CreateCuratorialKnowledge(repository).execute(
            CreateKnowledgeInput(
                caller=caller,
                kind=body.kind,
                content=body.content,
                registered_number=body.registeredNumber,
                observed_form=body.observedForm,
                institution_id=body.institutionId,
            )
        )
    except ValueError as exc:
        raise _unprocessable(str(exc)) from None
    await session.commit()
    return _knowledge_response(item)


@scientific_return_router.get(
    "/knowledge-items", response_model=list[KnowledgeItemResponse]
)
async def list_knowledge_items(
    caller: CallerPermission,
    repository: FullAgenticRepositoryDep,
    active_only: bool = Query(default=False, alias="activeOnly"),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[KnowledgeItemResponse]:
    items = await ListCuratorialKnowledge(repository).execute(
        caller, active_only=active_only, limit=limit
    )
    return [_knowledge_response(item) for item in items]


@scientific_return_router.put(
    "/knowledge-items/{item_id}", response_model=KnowledgeItemResponse
)
async def replace_knowledge_item(
    item_id: str,
    body: ReplaceKnowledgeRequest,
    caller: CallerPermission,
    repository: FullAgenticRepositoryDep,
    session: DBSession,
) -> KnowledgeItemResponse:
    try:
        item = await ReplaceCuratorialKnowledge(repository).execute(
            KnowledgeItemId(item_id),
            ReplaceKnowledgeInput(
                caller=caller,
                content=body.content,
                registered_number=body.registeredNumber,
                observed_form=body.observedForm,
            ),
        )
    except LookupError as exc:
        raise _not_found("SCIENTIFIC_RETURN_KNOWLEDGE_NOT_FOUND", str(exc)) from None
    except ValueError as exc:
        raise _unprocessable(str(exc)) from None
    await session.commit()
    return _knowledge_response(item)


@scientific_return_router.delete(
    "/knowledge-items/{item_id}", response_model=KnowledgeItemResponse
)
async def retire_knowledge_item(
    item_id: str,
    caller: CallerPermission,
    repository: FullAgenticRepositoryDep,
    session: DBSession,
) -> KnowledgeItemResponse:
    try:
        item = await RetireCuratorialKnowledge(repository).execute(
            KnowledgeItemId(item_id), caller
        )
    except LookupError as exc:
        raise _not_found("SCIENTIFIC_RETURN_KNOWLEDGE_NOT_FOUND", str(exc)) from None
    await session.commit()
    return _knowledge_response(item)


@scientific_return_router.post(
    "/knowledge-items/{item_id}/activate", response_model=KnowledgeItemResponse
)
async def activate_knowledge_item(
    item_id: str,
    caller: CallerPermission,
    repository: FullAgenticRepositoryDep,
    session: DBSession,
) -> KnowledgeItemResponse:
    try:
        item = await ActivateCuratorialKnowledge(repository).execute(
            KnowledgeItemId(item_id), caller
        )
    except LookupError as exc:
        raise _not_found("SCIENTIFIC_RETURN_KNOWLEDGE_NOT_FOUND", str(exc)) from None
    except ValueError as exc:
        raise _unprocessable(str(exc)) from None
    await session.commit()
    return _knowledge_response(item)


@scientific_return_router.post(
    "/candidates/{candidate_id}/knowledge-proposals",
    status_code=status.HTTP_201_CREATED,
    response_model=KnowledgeItemResponse,
)
async def propose_knowledge_from_decision(
    candidate_id: str,
    body: ProposeKnowledgeRequest,
    caller: CallerPermission,
    repository: Repository,
    knowledge_repository: FullAgenticRepositoryDep,
    reasoner: FullAgenticReasonerDep,
    session: DBSession,
) -> KnowledgeItemResponse:
    decisions = await repository.list_decisions(CandidatePublicationId(candidate_id))
    if not decisions:
        raise _not_found(
            "SCIENTIFIC_RETURN_DECISION_NOT_FOUND",
            f"Candidate {candidate_id} has no curator decision",
        )
    item = await ProposeKnowledgeFromDecision(knowledge_repository, reasoner).execute(
        decisions[-1], body.explanation, caller
    )
    await session.commit()
    return _knowledge_response(item)


def _not_found(code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"error": code, "message": message},
    )


def _unprocessable(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail={"error": "SCIENTIFIC_RETURN_INVALID", "message": message},
    )


def _watch_response(watch: ScientificReturnWatch) -> ScientificReturnWatchResponse:
    return ScientificReturnWatchResponse(
        id=watch.id,
        projectId=watch.project_id,
        status=watch.status,
        reviewIntervalDays=watch.review_interval_days,
        createdBy=watch.created_by,
        createdAt=watch.created_at,
        lastRunAt=watch.last_run_at,
        nextRunAt=watch.next_run_at,
        projectSnapshotId=watch.project_snapshot_id,
    )


async def _run_response(
    run: ScientificReturnSearchRun, repository: Repository
) -> ScientificReturnRunResponse:
    queries = await repository.list_queries(str(run.id))
    return ScientificReturnRunResponse(
        id=run.id,
        watchId=run.watch_id,
        status=run.status,
        startedAt=run.started_at,
        completedAt=run.completed_at,
        sourceCount=run.source_count,
        candidateCount=run.candidate_count,
        newCandidateCount=run.new_candidate_count,
        errorMessage=run.error_message,
        runKind=run.run_kind,
        queries=[
            ScientificReturnQueryResponse(
                id=query.id,
                source=query.source,
                queryText=query.query_text,
                queryType=query.query_type,
                sentAt=query.sent_at,
                resultCount=query.result_count,
                status=query.status,
                errorMessage=query.error_message,
            )
            for query in queries
        ],
    )


def _candidate_response(
    candidate: CandidatePublication,
) -> CandidatePublicationResponse:
    order = {"PRIMARY": 0, "SUPPORTING": 1, "WEAK": 2}
    evidences = sorted(candidate.evidences, key=lambda item: order[item.strength.value])
    return CandidatePublicationResponse(
        id=candidate.id,
        watchId=candidate.watch_id,
        source=candidate.source,
        sourceRecordId=candidate.source_record_id,
        doi=candidate.doi,
        title=candidate.title,
        authors=list(candidate.authors),
        publicationDate=candidate.publication_date,
        abstract=candidate.abstract,
        url=candidate.url,
        status=candidate.status,
        confirmedPublicationEntryId=candidate.confirmed_publication_entry_id,
        firstSeenAt=candidate.created_at,
        evidences=[
            CandidateEvidenceResponse(
                id=evidence.id,
                type=evidence.type,
                strength=evidence.strength,
                value=evidence.value,
                sourceField=evidence.source_field,
                explanation=evidence.explanation,
                objectId=evidence.object_id,
            )
            for evidence in evidences
        ],
        firstSeenKind=candidate.first_seen_kind,
        agenticCreated=candidate.agentic_created,
        agenticRediscovered=candidate.agentic_rediscovered,
    )


def _agent_analysis_response(
    analysis: CandidateAgentAnalysis,
) -> CandidateAgentAnalysisResponse:
    result = analysis.result
    return CandidateAgentAnalysisResponse(
        id=analysis.id,
        candidateId=analysis.candidate_id,
        runId=analysis.run_id,
        status=analysis.status,
        model=analysis.model,
        promptVersionId=analysis.prompt_version_id,
        promptVersion=analysis.prompt_version,
        inputHash=analysis.input_hash,
        responseHash=analysis.response_hash,
        analysis=(
            CandidateAgentAnalysisResultResponse(
                summary=result.summary,
                supportingEvidence=list(result.supporting_evidence),
                contradictions=list(result.contradictions),
                missingEvidence=list(result.missing_evidence),
                recommendedAction=result.recommended_action,
                proposedQueries=list(result.proposed_queries),
                reasoningSummary=result.reasoning_summary,
                confidence=result.confidence,
            )
            if result is not None
            else None
        ),
        startedAt=analysis.started_at,
        completedAt=analysis.completed_at,
        latencyMs=analysis.latency_ms,
        errorMessage=analysis.error_message,
        createdBy=analysis.created_by,
        staffFeedback=analysis.staff_feedback,
        feedbackComment=analysis.feedback_comment,
        feedbackBy=analysis.feedback_by,
        feedbackAt=analysis.feedback_at,
    )


@scientific_return_router.get(
    "/metrics", response_model=ScientificReturnMetricsResponse
)
async def get_metrics(
    caller: CallerPermission,
    repository: Repository,
) -> ScientificReturnMetricsResponse:
    require_staff(caller)
    metrics = await repository.get_metrics()
    return ScientificReturnMetricsResponse(
        activeWatches=metrics.active_watches,
        runs=metrics.runs,
        failedRuns=metrics.failed_runs,
        pendingCandidates=metrics.pending_candidates,
        confirmedCandidates=metrics.confirmed_candidates,
        dismissedCandidates=metrics.dismissed_candidates,
        fullAgentic=FullAgenticMetricsResponse(
            runs=metrics.full_agentic_runs,
            failedRuns=metrics.full_agentic_failed_runs,
            pendingCandidates=metrics.full_agentic_pending_candidates,
            confirmedCandidates=metrics.full_agentic_confirmed_candidates,
            dismissedCandidates=metrics.full_agentic_dismissed_candidates,
        ),
    )


def _correction_response(
    correction: CandidateCorrection | None,
) -> CandidateCorrectionRequest | None:
    if correction is None:
        return None
    return CandidateCorrectionRequest(
        title=correction.title,
        doi=correction.doi,
        url=correction.url,
        authors=list(correction.authors) if correction.authors is not None else None,
    )


def _grounded_form_responses(
    forms: Sequence[GroundedInventoryForm] | Sequence[Mapping[str, str | None]],
) -> list[GroundedInventoryFormResponse]:
    """Project grounded forms from either the decision VO or the queue row."""
    responses: list[GroundedInventoryFormResponse] = []
    for form in forms:
        if isinstance(form, GroundedInventoryForm):
            responses.append(
                GroundedInventoryFormResponse(
                    observedForm=form.observed_form,
                    sourceField=form.source_field.value,
                    sourceLocator=form.source_locator,
                )
            )
            continue
        observed = form.get("observedForm") or form.get("observed_form")
        field = form.get("sourceField") or form.get("source_field")
        if not observed or not field:
            continue
        responses.append(
            GroundedInventoryFormResponse(
                observedForm=str(observed),
                sourceField=str(field),
                sourceLocator=form.get("sourceLocator") or form.get("source_locator"),
            )
        )
    return responses


def _decision_response(decision: CandidateDecision) -> CandidateDecisionResponse:
    context = decision.decision_context
    return CandidateDecisionResponse(
        id=decision.id,
        candidateId=decision.candidate_id,
        decision=decision.decision,
        justification=decision.justification,
        decidedBy=decision.decided_by,
        decidedAt=decision.decided_at,
        evidenceSnapshot=list(decision.evidence_snapshot),
        correction=_correction_response(decision.correction),
        decisionContext=(
            CandidateDecisionContextResponse(
                version=context.version,
                passages=list(context.passages),
                inventoryForms=list(context.inventory_forms),
                queries=list(context.queries),
                sources=list(context.sources),
                explanation=context.explanation,
                confidence=context.confidence,
                contradictions=list(context.contradictions),
                knowledgeItemIds=list(context.knowledge_item_ids),
                discoveryBasis=context.discovery_basis,
                searchIntent=context.search_intent,
                searchStrategy=context.search_strategy,
                inventoryEvidenceStatus=context.inventory_evidence_status,
                groundedInventoryForms=_grounded_form_responses(
                    context.grounded_inventory_forms
                ),
            )
            if context is not None
            else None
        ),
    )


@scientific_return_router.post(
    "/projects/{project_id}/watch",
    status_code=status.HTTP_201_CREATED,
    response_model=ScientificReturnWatchResponse,
)
async def activate_watch(
    project_id: str,
    body: ActivateWatchRequest,
    caller: CallerPermission,
    repository: Repository,
    project_provider: ProjectProvider,
    session: DBSession,
) -> ScientificReturnWatchResponse:
    try:
        watch = await ActivateScientificReturnWatch(
            repository, project_provider
        ).execute(
            ActivateWatchInput(
                project_id=project_id,
                review_interval_days=body.reviewIntervalDays,
                caller=caller,
            )
        )
    except LookupError as exc:
        raise _not_found("COMPLETED_PROJECT_NOT_FOUND", str(exc)) from None
    except ValueError as exc:
        raise _unprocessable(str(exc)) from None
    await session.commit()
    return _watch_response(watch)


@scientific_return_router.get(
    "/projects/{project_id}/watch", response_model=ScientificReturnWatchResponse
)
async def get_watch(
    project_id: str,
    caller: CallerPermission,
    repository: Repository,
) -> ScientificReturnWatchResponse:
    require_staff(caller)
    watch = await repository.get_watch_by_project(project_id)
    if watch is None:
        raise _not_found(
            "SCIENTIFIC_RETURN_WATCH_NOT_FOUND",
            f"No scientific-return watch exists for project {project_id}",
        )
    return _watch_response(watch)


@scientific_return_router.patch(
    "/watches/{watch_id}", response_model=ScientificReturnWatchResponse
)
async def update_watch(
    watch_id: str,
    body: UpdateWatchRequest,
    caller: CallerPermission,
    repository: Repository,
    session: DBSession,
) -> ScientificReturnWatchResponse:
    """Change the status, the review cadence, or both.

    Applied in this order on purpose: re-cadencing a watch that is being closed
    in the same request would compute a next review nobody will ever act on.
    """
    if body.status is None and body.reviewIntervalDays is None:
        raise _unprocessable("Provide status or reviewIntervalDays")
    watch_key = ScientificReturnWatchId(watch_id)
    watch: ScientificReturnWatch | None = None
    try:
        if body.reviewIntervalDays is not None:
            watch = await ChangeWatchReviewInterval(repository).execute(
                watch_key, body.reviewIntervalDays, caller
            )
        if body.status is not None:
            watch = await ChangeWatchStatus(repository).execute(
                watch_key, body.status, caller
            )
    except WatchNotFound as exc:
        raise _not_found("SCIENTIFIC_RETURN_WATCH_NOT_FOUND", str(exc)) from None
    except ValueError as exc:
        raise _unprocessable(str(exc)) from None
    assert watch is not None  # one of the two branches always runs
    await session.commit()
    return _watch_response(watch)


@scientific_return_router.post(
    "/watches/{watch_id}/runs",
    status_code=status.HTTP_201_CREATED,
    response_model=ScientificReturnRunResponse,
)
async def run_watch(
    watch_id: str,
    caller: CallerPermission,
    repository: Repository,
    sources: BibliographicSources,
    result_limit: ResultLimit,
    max_queries: MaxQueries,
    notifications: Notifications,
    session: DBSession,
) -> ScientificReturnRunResponse:
    try:
        run = await RunScientificReturnSearch(
            repository,
            sources,
            result_limit,
            max_queries,
        ).execute(ScientificReturnWatchId(watch_id), caller)
    except WatchNotFound as exc:
        raise _not_found("SCIENTIFIC_RETURN_WATCH_NOT_FOUND", str(exc)) from None
    except ValueError as exc:
        raise _unprocessable(str(exc)) from None
    await session.commit()
    if run.new_candidate_count:
        watch = await repository.get_watch(ScientificReturnWatchId(watch_id))
        if watch is not None:
            try:
                await notifications.notify(
                    recipient_permission_id=watch.created_by,
                    kind=NotificationKind.SCIENTIFIC_RETURN_CANDIDATES_FOUND,
                    triggered_by=caller.id,
                    related_resource_type=RelatedResourceType.PROJECT,
                    related_resource_id=watch.project_id,
                    note=(
                        f"Scientific return found {run.new_candidate_count} new "
                        "candidate(s) for review."
                    ),
                )
                await session.commit()
            except Exception:
                await session.rollback()
                logger.exception("Could not notify scientific-return run %s.", run.id)
    return await _run_response(run, repository)


@scientific_return_router.get(
    "/watches/{watch_id}/runs", response_model=PaginatedRunsResponse
)
async def list_runs(
    watch_id: str,
    caller: CallerPermission,
    repository: Repository,
    page: int = Query(0, ge=0),
    size: int = Query(10, ge=1, le=100),
) -> PaginatedRunsResponse:
    require_staff(caller)
    items, total = await repository.list_runs(
        ScientificReturnWatchId(watch_id), page, size
    )
    return PaginatedRunsResponse(
        content=[await _run_response(item, repository) for item in items],
        page=page,
        size=size,
        totalElements=total,
        totalPages=ceil(total / size) if total else 0,
    )


@scientific_return_router.get(
    "/projects/{project_id}/candidates", response_model=PaginatedCandidatesResponse
)
async def list_candidates(
    project_id: str,
    caller: CallerPermission,
    repository: Repository,
    candidate_status: Annotated[CandidateStatus | None, Query(alias="status")] = None,
    page: int = Query(0, ge=0),
    size: int = Query(20, ge=1, le=100),
) -> PaginatedCandidatesResponse:
    require_staff(caller)
    items, total = await repository.list_candidates(
        project_id, candidate_status, page, size
    )
    return PaginatedCandidatesResponse(
        content=[_candidate_response(item) for item in items],
        page=page,
        size=size,
        totalElements=total,
        totalPages=ceil(total / size) if total else 0,
    )


@scientific_return_router.get(
    "/candidates", response_model=PaginatedCandidateQueueResponse
)
async def list_candidate_queue(
    caller: CallerPermission,
    repository: Repository,
    candidate_status: Annotated[CandidateStatus | None, Query(alias="status")] = (
        CandidateStatus.PENDING
    ),
    project_id: Annotated[str | None, Query(alias="projectId")] = None,
    source: str | None = None,
    evidence_strength: Annotated[
        EvidenceStrength | None, Query(alias="evidenceStrength")
    ] = None,
    page: int = Query(0, ge=0),
    size: int = Query(20, ge=1, le=100),
) -> PaginatedCandidateQueueResponse:
    require_staff(caller)
    items, total = await repository.list_candidate_queue(
        candidate_status,
        project_id,
        source,
        evidence_strength,
        page,
        size,
    )
    return PaginatedCandidateQueueResponse(
        content=[
            CandidateReviewItemResponse(
                **_candidate_response(item.candidate).model_dump(),
                projectId=item.project_id,
                discoveryBasis=item.discovery_basis,
                searchIntent=item.search_intent,
                searchStrategy=item.search_strategy,
                inventoryEvidenceStatus=(
                    InventoryEvidenceStatus(item.inventory_evidence_status)
                    if item.inventory_evidence_status
                    else None
                ),
                groundedInventoryForms=_grounded_form_responses(
                    item.grounded_inventory_forms
                ),
                groundedPassages=list(item.grounded_passages),
                rejectedPassageCount=item.rejected_passage_count,
                rejectedInventoryFormCount=item.rejected_inventory_form_count,
            )
            for item in items
        ],
        page=page,
        size=size,
        totalElements=total,
        totalPages=ceil(total / size) if total else 0,
    )


@scientific_return_router.post(
    "/candidates/{candidate_id}/decision",
    response_model=CandidatePublicationResponse,
)
async def decide_candidate(
    candidate_id: str,
    body: CandidateDecisionRequest,
    caller: CallerPermission,
    repository: Repository,
    publication_writer: PublicationWriter,
    session: DBSession,
) -> CandidatePublicationResponse:
    correction = (
        CandidateCorrection(
            title=body.correction.title,
            doi=body.correction.doi,
            url=body.correction.url,
            authors=(
                tuple(body.correction.authors)
                if body.correction.authors is not None
                else None
            ),
        )
        if body.correction is not None
        else None
    )
    try:
        candidate = await DecideCandidate(repository, publication_writer).execute(
            DecideCandidateInput(
                candidate_id=CandidatePublicationId(candidate_id),
                decision=body.decision,
                caller=caller,
                justification=body.justification,
                correction=correction,
            )
        )
    except CandidateNotFound as exc:
        raise _not_found("SCIENTIFIC_RETURN_CANDIDATE_NOT_FOUND", str(exc)) from None
    except ValueError as exc:
        raise _unprocessable(str(exc)) from None
    await session.commit()
    return _candidate_response(candidate)


@scientific_return_router.get(
    "/candidates/{candidate_id}/decisions",
    response_model=list[CandidateDecisionResponse],
)
async def list_candidate_decisions(
    candidate_id: str,
    caller: CallerPermission,
    repository: Repository,
) -> list[CandidateDecisionResponse]:
    require_staff(caller)
    decisions = await repository.list_decisions(CandidatePublicationId(candidate_id))
    return [_decision_response(item) for item in decisions]


@scientific_return_router.get(
    "/candidates/{candidate_id}/agent-analyses",
    response_model=list[CandidateAgentAnalysisResponse],
)
async def list_candidate_agent_analyses(
    candidate_id: str,
    caller: CallerPermission,
    repository: Repository,
) -> list[CandidateAgentAnalysisResponse]:
    try:
        analyses = await ListCandidateAgentAnalyses(repository).execute(
            CandidatePublicationId(candidate_id), caller
        )
    except CandidateNotFound as exc:
        raise _not_found("SCIENTIFIC_RETURN_CANDIDATE_NOT_FOUND", str(exc)) from None
    return [_agent_analysis_response(item) for item in analyses]


@scientific_return_router.post(
    "/agent-analyses/{analysis_id}/feedback",
    response_model=CandidateAgentAnalysisResponse,
)
async def record_agent_analysis_feedback(
    analysis_id: str,
    body: AgentAnalysisFeedbackRequest,
    caller: CallerPermission,
    repository: Repository,
    session: DBSession,
) -> CandidateAgentAnalysisResponse:
    try:
        analysis = await RecordAgentAnalysisFeedback(repository).execute(
            RecordAgentAnalysisFeedbackInput(
                analysis_id=CandidateAgentAnalysisId(analysis_id),
                feedback=body.feedback,
                comment=body.comment,
                caller=caller,
            )
        )
    except AgentAnalysisNotFound as exc:
        raise _not_found(
            "SCIENTIFIC_RETURN_AGENT_ANALYSIS_NOT_FOUND", str(exc)
        ) from None
    except ValueError as exc:
        raise _unprocessable(str(exc)) from None
    await session.commit()
    return _agent_analysis_response(analysis)


def _iteration_response(
    iteration: InvestigationIteration,
) -> InvestigationIterationResponse:
    observation = iteration.observation
    plan = iteration.plan
    decision = iteration.policy_decision
    tool = iteration.tool_result
    delta = iteration.evidence_delta
    reflection = iteration.reflection
    telemetry = iteration.telemetry
    return InvestigationIterationResponse(
        id=str(iteration.id),
        number=iteration.number,
        status=iteration.status,
        startedAt=iteration.started_at,
        completedAt=iteration.completed_at,
        observation=(
            None
            if observation is None
            else InvestigationObservationResponse(
                researcher=observation.researcher,
                projectReference=observation.project_reference,
                objects=[
                    {
                        "id": item.object_id,
                        "inventoryNumber": item.inventory_number,
                        "objectName": item.object_name,
                    }
                    for item in observation.objects
                ],
                triedQueries=list(observation.tried_queries),
                allowedActions=[item.value for item in observation.allowed_actions],
            )
        ),
        plan=(
            None
            if plan is None
            else InvestigationPlanResponse(
                objective=plan.objective,
                actionType=plan.action.type,
                objectId=plan.action.object_id,
                reasoningSummary=plan.reasoning_summary,
                expectedEvidence=list(plan.expected_evidence),
            )
        ),
        policy=(
            None
            if decision is None
            else InvestigationPolicyResponse(
                authorized=decision.authorized,
                justification=decision.justification,
                rejectionReason=decision.rejection_reason,
            )
        ),
        tool=(
            None
            if tool is None
            else InvestigationToolResponse(
                executedQueries=list(tool.executed_queries),
                sources=list(tool.sources),
                totalResults=tool.total_results,
                createdCandidateIds=list(tool.created_candidate_ids),
                addedEvidenceIds=list(tool.added_evidence_ids),
            )
        ),
        evidenceDelta=(
            None
            if delta is None
            else InvestigationDeltaResponse(
                added=list(delta.added),
                preserved=list(delta.preserved),
                removed=list(delta.removed),
            )
        ),
        reflection=(
            None
            if reflection is None
            else InvestigationReflectionResponse(
                progress=reflection.progress,
                evidenceDeltaSummary=reflection.evidence_delta_summary,
                remainingGaps=list(reflection.remaining_gaps),
                recommendedStop=reflection.recommended_stop,
                reasoningSummary=reflection.reasoning_summary,
            )
        ),
        telemetry=(
            None
            if telemetry is None
            else InvestigationTelemetryResponse(
                model=telemetry.model,
                promptVersion=telemetry.prompt_version,
                planLatencyMs=telemetry.plan_latency_ms,
                reflectionLatencyMs=telemetry.reflection_latency_ms,
                totalLatencyMs=telemetry.total_latency_ms,
            )
        ),
        evidenceBeforeHash=iteration.evidence_before_hash,
        evidenceAfterHash=iteration.evidence_after_hash,
        errorMessage=iteration.error_message,
    )


def _investigation_response(
    investigation: ScientificReturnInvestigation,
) -> InvestigationResponse:
    budget = investigation.budget
    return InvestigationResponse(
        id=str(investigation.id),
        watchId=str(investigation.watch_id),
        candidateId=(
            str(investigation.candidate_id) if investigation.candidate_id else None
        ),
        objective=investigation.objective,
        status=investigation.status,
        mode=investigation.mode,
        stopReason=investigation.stop_reason,
        currentIteration=investigation.current_iteration,
        budget=InvestigationBudgetResponse(
            maxIterations=budget.max_iterations,
            maxQueries=budget.max_queries,
            maxNewCandidates=budget.max_new_candidates,
            usedIterations=budget.used_iterations,
            usedQueries=budget.used_queries,
            createdCandidates=budget.created_candidates,
        ),
        startedAt=investigation.started_at,
        completedAt=investigation.completed_at,
        createdBy=str(investigation.created_by),
        previousInvestigationId=(
            str(investigation.previous_investigation_id)
            if investigation.previous_investigation_id
            else None
        ),
        iterations=[_iteration_response(item) for item in investigation.iterations],
    )


async def _run_investigation(
    watch_id: ScientificReturnWatchId,
    objective: InvestigationObjective,
    candidate_id: CandidatePublicationId | None,
    caller: Actor,
    use_case: RunScientificReturnInvestigation,
    idempotency_key: str | None = None,
) -> InvestigationResponse:
    try:
        investigation = await use_case.execute(
            RunInvestigationInput(
                watch_id=watch_id,
                objective=objective,
                caller=caller,
                candidate_id=candidate_id,
                idempotency_key=idempotency_key,
            )
        )
    except InvestigationDisabled as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "SCIENTIFIC_RETURN_AGENT_DISABLED", "message": str(exc)},
        ) from None
    except InvestigationAlreadyRunning as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "SCIENTIFIC_RETURN_INVESTIGATION_RUNNING",
                "message": str(exc),
            },
        ) from None
    except InvestigationNotPossible as exc:
        raise _unprocessable(str(exc)) from None
    return _investigation_response(investigation)


@scientific_return_router.post(
    "/watches/{watch_id}/investigations",
    status_code=status.HTTP_201_CREATED,
    response_model=InvestigationResponse,
)
async def start_watch_investigation(
    watch_id: str,
    caller: CallerPermission,
    use_case: InvestigationRunner,
    session: DBSession,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> InvestigationResponse:
    """Run a discovery investigation for a watch, synchronously.

    The cycle is one iteration and one action, so the response carries the whole
    trajectory already terminal. E3 turns this into 202 plus polling.
    """
    response = await _run_investigation(
        ScientificReturnWatchId(watch_id),
        InvestigationObjective.DISCOVER_CANDIDATE,
        None,
        caller,
        use_case,
        idempotency_key,
    )
    await session.commit()
    return response


@scientific_return_router.post(
    "/candidates/{candidate_id}/investigations",
    status_code=status.HTTP_201_CREATED,
    response_model=InvestigationResponse,
)
async def start_candidate_investigation(
    candidate_id: str,
    caller: CallerPermission,
    repository: Repository,
    use_case: InvestigationRunner,
    session: DBSession,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> InvestigationResponse:
    candidate = await repository.get_candidate(CandidatePublicationId(candidate_id))
    if candidate is None:
        raise _not_found(
            "SCIENTIFIC_RETURN_CANDIDATE_NOT_FOUND",
            f"Candidate {candidate_id} not found",
        )
    response = await _run_investigation(
        candidate.watch_id,
        InvestigationObjective.ENRICH_CANDIDATE,
        candidate.id,
        caller,
        use_case,
        idempotency_key,
    )
    await session.commit()
    return response


@scientific_return_router.get(
    "/watches/{watch_id}/investigations",
    response_model=list[InvestigationResponse],
)
async def list_watch_investigations(
    watch_id: str,
    caller: CallerPermission,
    investigations: InvestigationRepository,
) -> list[InvestigationResponse]:
    require_staff(caller)
    found = await investigations.list_for_watch(ScientificReturnWatchId(watch_id))
    return [_investigation_response(item) for item in found]


@scientific_return_router.get(
    "/candidates/{candidate_id}/investigations",
    response_model=list[InvestigationResponse],
)
async def list_candidate_investigations(
    candidate_id: str,
    caller: CallerPermission,
    investigations: InvestigationRepository,
) -> list[InvestigationResponse]:
    require_staff(caller)
    found = await investigations.list_for_candidate(
        CandidatePublicationId(candidate_id)
    )
    return [_investigation_response(item) for item in found]


@scientific_return_router.get(
    "/investigations/{investigation_id}",
    response_model=InvestigationResponse,
)
async def get_investigation(
    investigation_id: str,
    caller: CallerPermission,
    investigations: InvestigationRepository,
) -> InvestigationResponse:
    """Read one investigation. Never continues or re-runs the cycle."""
    require_staff(caller)
    found = await investigations.get(InvestigationId(investigation_id))
    if found is None:
        raise _not_found(
            "SCIENTIFIC_RETURN_INVESTIGATION_NOT_FOUND",
            f"Investigation {investigation_id} not found",
        )
    return _investigation_response(found)
