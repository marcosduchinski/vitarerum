from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.scientific_return.domain.enums import (
    AgentAnalysisFeedback,
    AgentAnalysisStatus,
    AgentConfidence,
    AgentRecommendedAction,
    CandidateStatus,
    DecisionType,
    EvidenceStrength,
    EvidenceType,
    QueryStatus,
    QueryType,
    RunStatus,
    WatchStatus,
)


class ActivateWatchRequest(BaseModel):
    reviewIntervalDays: int = Field(default=90, ge=1, le=365)


class ChangeWatchStatusRequest(BaseModel):
    status: WatchStatus


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


class ScientificReturnMetricsResponse(BaseModel):
    activeWatches: int
    runs: int
    failedRuns: int
    pendingCandidates: int
    confirmedCandidates: int
    dismissedCandidates: int


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


class PaginatedCandidatesResponse(BaseModel):
    content: list[CandidatePublicationResponse]
    page: int
    size: int
    totalElements: int
    totalPages: int


class CandidateReviewItemResponse(CandidatePublicationResponse):
    projectId: str


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


class CandidateDecisionResponse(BaseModel):
    id: str
    candidateId: str
    decision: DecisionType
    justification: str | None
    decidedBy: str
    decidedAt: datetime
    evidenceSnapshot: list[dict[str, str]]
    correction: CandidateCorrectionRequest | None


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
    mode: str = "SHADOW"
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
