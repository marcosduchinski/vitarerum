from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.scientific_return.domain.enums import (
    AgentAnalysisFeedback,
    AgentAnalysisStatus,
    AgentConfidence,
    AgenticTrajectoryEventKind,
    AgentProgress,
    AgentRecommendedAction,
    CandidateStatus,
    DecisionType,
    EvidenceStrength,
    EvidenceType,
    FullAgenticInvestigationStatus,
    InventoryEvidenceStatus,
    InvestigationMode,
    InvestigationObjective,
    InvestigationStatus,
    IterationStatus,
    KnowledgeKind,
    KnowledgeStatus,
    PolicyRejectionReason,
    QueryStatus,
    QueryType,
    RunKind,
    RunStatus,
    StopReason,
    WatchStatus,
)


class ActivateWatchRequest(BaseModel):
    reviewIntervalDays: int = Field(default=90, ge=1, le=365)


class UpdateWatchRequest(BaseModel):
    """Partial update. Both fields are optional; at least one must be present."""

    status: WatchStatus | None = None
    reviewIntervalDays: int | None = Field(default=None, ge=1, le=365)


class ScientificReturnWatchResponse(BaseModel):
    id: str
    projectId: str
    status: WatchStatus
    reviewIntervalDays: int
    createdBy: str
    createdAt: datetime
    lastRunAt: datetime | None
    nextRunAt: datetime
    projectSnapshotId: str


class ScientificReturnQueryResponse(BaseModel):
    id: str
    source: str
    queryText: str
    queryType: QueryType
    sentAt: datetime
    resultCount: int
    status: QueryStatus
    errorMessage: str | None


class ScientificReturnRunResponse(BaseModel):
    id: str
    watchId: str
    status: RunStatus
    startedAt: datetime
    completedAt: datetime | None
    sourceCount: int
    candidateCount: int
    newCandidateCount: int
    errorMessage: str | None
    queries: list[ScientificReturnQueryResponse] = Field(default_factory=list)
    runKind: RunKind = RunKind.DETERMINISTIC


class PaginatedRunsResponse(BaseModel):
    content: list[ScientificReturnRunResponse]
    page: int
    size: int
    totalElements: int
    totalPages: int


class CandidateEvidenceResponse(BaseModel):
    id: str
    type: EvidenceType
    strength: EvidenceStrength
    value: str
    sourceField: str
    explanation: str
    objectId: str | None


class FullAgenticMetricsResponse(BaseModel):
    runs: int
    failedRuns: int
    pendingCandidates: int
    confirmedCandidates: int
    dismissedCandidates: int


class FullAgenticReadinessResponse(BaseModel):
    enabled: bool
    requestedSources: list[str]
    operationalSources: list[str]
    unavailableSources: list[str]
    inspectableEvidenceSources: list[str]
    configurationValid: bool
    message: str | None = None


class ScientificReturnMetricsResponse(BaseModel):
    activeWatches: int
    runs: int
    failedRuns: int
    pendingCandidates: int
    confirmedCandidates: int
    dismissedCandidates: int
    fullAgentic: FullAgenticMetricsResponse | None = None


class CandidatePublicationResponse(BaseModel):
    id: str
    watchId: str
    source: str
    sourceRecordId: str
    doi: str | None
    title: str
    authors: list[str]
    publicationDate: str | None
    abstract: str | None
    url: str | None
    status: CandidateStatus
    snoozedUntil: datetime | None
    confirmedPublicationEntryId: str | None
    firstSeenAt: datetime
    evidences: list[CandidateEvidenceResponse]
    firstSeenKind: RunKind = RunKind.DETERMINISTIC
    agenticCreated: bool = False
    agenticRediscovered: bool = False


class PaginatedCandidatesResponse(BaseModel):
    content: list[CandidatePublicationResponse]
    page: int
    size: int
    totalElements: int
    totalPages: int


class GroundedInventoryFormResponse(BaseModel):
    observedForm: str
    sourceField: str
    sourceLocator: str | None = None


class CandidateReviewItemResponse(CandidatePublicationResponse):
    projectId: str
    discoveryBasis: str | None = None
    searchIntent: str | None = None
    searchStrategy: str | None = None
    inventoryEvidenceStatus: InventoryEvidenceStatus | None = None
    groundedInventoryForms: list[GroundedInventoryFormResponse] = Field(
        default_factory=list
    )
    groundedPassages: list[str] = Field(default_factory=list)
    rejectedPassageCount: int = Field(default=0, ge=0)
    rejectedInventoryFormCount: int = Field(default=0, ge=0)


class PaginatedCandidateQueueResponse(BaseModel):
    content: list[CandidateReviewItemResponse]
    page: int
    size: int
    totalElements: int
    totalPages: int


class CandidateCorrectionRequest(BaseModel):
    title: str | None = None
    doi: str | None = None
    url: str | None = None
    authors: list[str] | None = None


class CandidateDecisionRequest(BaseModel):
    decision: DecisionType
    justification: str | None = Field(default=None, max_length=2000)
    snoozedUntil: datetime | None = None
    correction: CandidateCorrectionRequest | None = None


class CandidateDecisionContextResponse(BaseModel):
    version: int
    passages: list[str]
    inventoryForms: list[str]
    queries: list[str]
    sources: list[str]
    explanation: str
    confidence: AgentConfidence
    contradictions: list[str]
    knowledgeItemIds: list[str]
    discoveryBasis: str | None = None
    searchIntent: str | None = None
    searchStrategy: str | None = None
    inventoryEvidenceStatus: InventoryEvidenceStatus | None = None
    groundedInventoryForms: list[GroundedInventoryFormResponse] = Field(
        default_factory=list
    )


class CandidateDecisionResponse(BaseModel):
    id: str
    candidateId: str
    decision: DecisionType
    justification: str | None
    decidedBy: str
    decidedAt: datetime
    evidenceSnapshot: list[dict[str, str]]
    correction: CandidateCorrectionRequest | None
    decisionContext: CandidateDecisionContextResponse | None = None


class CandidateAgentAnalysisResultResponse(BaseModel):
    summary: str
    supportingEvidence: list[str]
    contradictions: list[str]
    missingEvidence: list[str]
    recommendedAction: AgentRecommendedAction
    proposedQueries: list[str]
    reasoningSummary: str
    confidence: AgentConfidence


class CandidateAgentAnalysisResponse(BaseModel):
    id: str
    candidateId: str
    runId: str
    status: AgentAnalysisStatus
    model: str
    promptVersionId: str
    promptVersion: str
    inputHash: str
    responseHash: str | None
    analysis: CandidateAgentAnalysisResultResponse | None
    startedAt: datetime
    completedAt: datetime | None
    latencyMs: int | None
    errorMessage: str | None
    createdBy: str
    staffFeedback: AgentAnalysisFeedback | None
    feedbackComment: str | None
    feedbackBy: str | None
    feedbackAt: datetime | None


class AgentAnalysisFeedbackRequest(BaseModel):
    feedback: AgentAnalysisFeedback
    comment: str | None = Field(default=None, max_length=2000)


class StartInvestigationRequest(BaseModel):
    objective: InvestigationObjective


class InvestigationObservationResponse(BaseModel):
    researcher: str
    projectReference: str
    objects: list[dict[str, str]]
    triedQueries: list[str]
    allowedActions: list[str]


class InvestigationPlanResponse(BaseModel):
    objective: str
    actionType: AgentRecommendedAction
    objectId: str | None
    reasoningSummary: str
    expectedEvidence: list[EvidenceType]


class InvestigationPolicyResponse(BaseModel):
    authorized: bool
    justification: str
    rejectionReason: PolicyRejectionReason | None


class InvestigationToolResponse(BaseModel):
    executedQueries: list[str]
    sources: list[str]
    totalResults: int
    createdCandidateIds: list[str]
    addedEvidenceIds: list[str]


class InvestigationDeltaResponse(BaseModel):
    added: list[EvidenceType]
    preserved: list[EvidenceType]
    removed: list[EvidenceType]


class InvestigationReflectionResponse(BaseModel):
    progress: AgentProgress
    evidenceDeltaSummary: str
    remainingGaps: list[str]
    recommendedStop: bool
    reasoningSummary: str


class InvestigationTelemetryResponse(BaseModel):
    model: str
    promptVersion: str
    planLatencyMs: int
    reflectionLatencyMs: int
    totalLatencyMs: int


class InvestigationIterationResponse(BaseModel):
    id: str
    number: int
    status: IterationStatus
    startedAt: datetime
    completedAt: datetime | None
    observation: InvestigationObservationResponse | None
    plan: InvestigationPlanResponse | None
    policy: InvestigationPolicyResponse | None
    tool: InvestigationToolResponse | None
    evidenceDelta: InvestigationDeltaResponse | None
    reflection: InvestigationReflectionResponse | None
    telemetry: InvestigationTelemetryResponse | None
    evidenceBeforeHash: str | None
    evidenceAfterHash: str | None
    errorMessage: str | None


class InvestigationBudgetResponse(BaseModel):
    maxIterations: int
    maxQueries: int
    maxNewCandidates: int
    usedIterations: int
    usedQueries: int
    createdCandidates: int


class InvestigationResponse(BaseModel):
    id: str
    watchId: str
    candidateId: str | None
    objective: InvestigationObjective
    status: InvestigationStatus
    mode: InvestigationMode
    stopReason: StopReason | None
    currentIteration: int
    budget: InvestigationBudgetResponse
    startedAt: datetime
    completedAt: datetime | None
    createdBy: str
    previousInvestigationId: str | None
    iterations: list[InvestigationIterationResponse]


class CreateKnowledgeRequest(BaseModel):
    kind: KnowledgeKind
    content: str = Field(min_length=1, max_length=4000)
    registeredNumber: str | None = Field(default=None, max_length=255)
    observedForm: str | None = Field(default=None, max_length=255)
    institutionId: str | None = None


class ReplaceKnowledgeRequest(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    registeredNumber: str | None = Field(default=None, max_length=255)
    observedForm: str | None = Field(default=None, max_length=255)


class ProposeKnowledgeRequest(BaseModel):
    explanation: str = Field(min_length=1, max_length=2000)


class KnowledgeItemResponse(BaseModel):
    id: str
    institutionId: str | None
    kind: KnowledgeKind
    status: KnowledgeStatus
    content: str
    registeredNumber: str | None
    observedForm: str | None
    supersedesId: str | None
    sourceCandidateId: str | None
    sourceDecisionId: str | None
    createdBy: str
    createdAt: datetime
    validatedBy: str | None
    validatedAt: datetime | None
    retiredBy: str | None
    retiredAt: datetime | None


class StartFullAgenticRequest(BaseModel):
    objective: InvestigationObjective = InvestigationObjective.DISCOVER_CANDIDATE
    candidateId: str | None = None


class AgenticTrajectoryEventResponse(BaseModel):
    id: str
    sequence: int
    kind: AgenticTrajectoryEventKind
    payload: dict[str, object]
    occurredAt: datetime


class FullAgenticInvestigationResponse(BaseModel):
    id: str
    watchId: str
    objective: InvestigationObjective
    candidateId: str | None
    searchRunId: str | None
    status: FullAgenticInvestigationStatus
    budget: dict[str, int]
    usage: dict[str, int]
    createdBy: str
    createdAt: datetime
    startedAt: datetime | None
    completedAt: datetime | None
    heartbeatAt: datetime | None
    failureReason: str | None
    degradedReason: str | None = None


class ExecuteFullAgenticRequest(BaseModel):
    investigationId: str
