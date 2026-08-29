import { Page } from '@shared/models/page.model';

export type ScientificReturnWatchStatus = 'ACTIVE' | 'PAUSED' | 'CLOSED';
export type ScientificReturnWatchIneligibilityReason =
  | 'NO_CONSULTED_OBJECTS'
  | 'MISSING_INVENTORY_NUMBER'
  | 'MISSING_OBJECT_NAME'
  | 'REQUESTER_NOT_FOUND'
  | 'PROJECT_NOT_COMPLETED';
export type ScientificReturnRunStatus = 'RUNNING' | 'COMPLETED' | 'FAILED';
export type ScientificReturnQueryStatus = 'COMPLETED' | 'FAILED';
export type ScientificReturnCandidateStatus = 'PENDING' | 'CONFIRMED' | 'DISMISSED';
export type ScientificReturnDecision = 'CONFIRM' | 'CORRECT_AND_CONFIRM' | 'DISMISS';
export type ScientificReturnEvidenceStrength = 'PRIMARY' | 'SUPPORTING' | 'WEAK';
export type ScientificReturnEvidenceType =
  | 'INVENTORY_NUMBER'
  | 'AUTHOR'
  | 'OBJECT_NAME'
  | 'AUTHOR_INVENTORY'
  | 'INVENTORY_OBJECT'
  | 'AUTHOR_OBJECT';
export type ScientificReturnAgentAnalysisStatus = 'RUNNING' | 'COMPLETED' | 'FAILED';
export type ScientificReturnAgentConfidence = 'LOW' | 'MEDIUM' | 'HIGH';
export type ScientificReturnAgentFeedback = 'USEFUL' | 'PARTIALLY_USEFUL' | 'NOT_USEFUL';
export type InventoryEvidenceStatus = 'VERIFIED' | 'NOT_OBSERVED' | 'UNAVAILABLE';

export interface GroundedInventoryForm {
  readonly observedForm: string;
  readonly sourceField: 'TITLE' | 'ABSTRACT' | 'INDEXED_TEXT';
  readonly sourceLocator: string | null;
}
export type ScientificReturnAgentAction =
  | 'PRESENT_FOR_REVIEW'
  | 'SEARCH_INVENTORY_VARIANTS'
  | 'SEARCH_AUTHOR_VARIANTS'
  | 'SEARCH_TAXON_VARIANTS'
  | 'SEARCH_FULL_TEXT'
  | 'DEPRIORITIZE'
  | 'STOP_INSUFFICIENT_EVIDENCE';

export interface ScientificReturnWatch {
  readonly id: string;
  readonly projectId: string;
  readonly status: ScientificReturnWatchStatus;
  readonly reviewIntervalDays: number;
  readonly createdBy: string;
  readonly createdAt: string;
  readonly lastRunAt: string | null;
  readonly nextRunAt: string;
  readonly scheduleAnchorAt: string;
  readonly projectSnapshotId: string;
}

export interface CreateScientificReturnWatchRequest {
  readonly reviewIntervalDays: number;
  readonly scheduleAnchorAt?: string;
  readonly startImmediately?: boolean;
}

export interface UpdateScientificReturnWatchRequest {
  readonly status?: ScientificReturnWatchStatus;
  readonly reviewIntervalDays?: number;
  readonly scheduleAnchorAt?: string;
}

export interface ScientificReturnWatchLookupItem {
  readonly projectId: string;
  readonly watch: ScientificReturnWatch | null;
  readonly eligible: boolean;
  readonly ineligibilityReason: ScientificReturnWatchIneligibilityReason | null;
}

export interface ScientificReturnWatchLookupResponse {
  readonly items: readonly ScientificReturnWatchLookupItem[];
}

export interface ScientificReturnQuery {
  readonly id: string;
  readonly source: string;
  readonly queryText: string;
  readonly queryType:
    | 'INVENTORY'
    | 'AUTHOR_INVENTORY'
    | 'INVENTORY_OBJECT'
    | 'AUTHOR_OBJECT'
    | 'AGENTIC';
  readonly sentAt: string;
  readonly resultCount: number;
  readonly status: ScientificReturnQueryStatus;
  readonly errorMessage: string | null;
}

export interface ScientificReturnRun {
  readonly id: string;
  readonly watchId: string;
  readonly status: ScientificReturnRunStatus;
  readonly startedAt: string;
  readonly completedAt: string | null;
  readonly sourceCount: number;
  readonly candidateCount: number;
  readonly newCandidateCount: number;
  readonly errorMessage: string | null;
  readonly queries: readonly ScientificReturnQuery[];
  readonly runKind?: 'DETERMINISTIC' | 'FULL_AGENTIC';
}

export interface ScientificReturnEvidence {
  readonly id: string;
  readonly type: string;
  readonly strength: ScientificReturnEvidenceStrength;
  readonly value: string;
  readonly sourceField: string;
  readonly explanation: string;
  readonly objectId: string | null;
}

export interface ScientificReturnCandidate {
  readonly id: string;
  readonly watchId: string;
  readonly source: string;
  readonly sourceRecordId: string;
  readonly doi: string | null;
  readonly title: string;
  readonly authors: readonly string[];
  readonly publicationDate: string | null;
  readonly abstract: string | null;
  readonly url: string | null;
  readonly status: ScientificReturnCandidateStatus;
  readonly confirmedPublicationEntryId: string | null;
  readonly firstSeenAt: string;
  readonly evidences: readonly ScientificReturnEvidence[];
  readonly firstSeenKind?: 'DETERMINISTIC' | 'FULL_AGENTIC';
  readonly agenticCreated?: boolean;
  readonly agenticRediscovered?: boolean;
}

export interface ScientificReturnReviewItem extends ScientificReturnCandidate {
  readonly projectId: string;
  readonly discoveryBasis?: string | null;
  readonly searchIntent?: string | null;
  readonly searchStrategy?: string | null;
  readonly inventoryEvidenceStatus?: InventoryEvidenceStatus | null;
  readonly groundedInventoryForms?: readonly GroundedInventoryForm[];
  readonly groundedPassages: readonly string[];
  readonly rejectedPassageCount: number;
  readonly rejectedInventoryFormCount: number;
}

export interface ScientificReturnMetrics {
  readonly activeWatches: number;
  readonly runs: number;
  readonly failedRuns: number;
  readonly pendingCandidates: number;
  readonly confirmedCandidates: number;
  readonly dismissedCandidates: number;
  readonly fullAgentic?: {
    readonly runs: number;
    readonly failedRuns: number;
    readonly pendingCandidates: number;
    readonly confirmedCandidates: number;
    readonly dismissedCandidates: number;
  } | null;
}

export interface CandidateCorrection {
  readonly title: string | null;
  readonly doi: string | null;
  readonly url: string | null;
  readonly authors: readonly string[] | null;
}

export interface CandidateDecisionRequest {
  readonly decision: ScientificReturnDecision;
  readonly justification?: string | null;
  readonly correction?: CandidateCorrection | null;
}

export interface CandidateDecisionRecord {
  readonly id: string;
  readonly candidateId: string;
  readonly decision: ScientificReturnDecision;
  readonly justification: string | null;
  readonly decidedBy: string;
  readonly decidedAt: string;
  readonly evidenceSnapshot: readonly Record<string, string>[];
  readonly correction: CandidateCorrection | null;
  readonly decisionContext?: CandidateDecisionContext | null;
}

export interface CandidateDecisionContext {
  readonly version: number;
  readonly passages: readonly string[];
  readonly inventoryForms: readonly string[];
  readonly queries: readonly string[];
  readonly sources: readonly string[];
  readonly explanation: string;
  readonly confidence: ScientificReturnAgentConfidence;
  readonly contradictions: readonly string[];
  readonly knowledgeItemIds: readonly string[];
  readonly discoveryBasis?: string | null;
  readonly searchIntent?: string | null;
  readonly searchStrategy?: string | null;
  readonly inventoryEvidenceStatus?: InventoryEvidenceStatus | null;
  readonly groundedInventoryForms?: readonly GroundedInventoryForm[];
}

export interface CandidateAgentAnalysisResult {
  readonly summary: string;
  readonly supportingEvidence: readonly string[];
  readonly contradictions: readonly string[];
  readonly missingEvidence: readonly string[];
  readonly recommendedAction: ScientificReturnAgentAction;
  readonly proposedQueries: readonly string[];
  readonly reasoningSummary: string;
  readonly confidence: ScientificReturnAgentConfidence;
}

export interface CandidateAgentAnalysis {
  readonly id: string;
  readonly candidateId: string;
  readonly runId: string;
  readonly status: ScientificReturnAgentAnalysisStatus;
  readonly model: string;
  readonly promptVersionId: string;
  readonly promptVersion: string;
  readonly inputHash: string;
  readonly responseHash: string | null;
  readonly analysis: CandidateAgentAnalysisResult | null;
  readonly startedAt: string;
  readonly completedAt: string | null;
  readonly latencyMs: number | null;
  readonly errorMessage: string | null;
  readonly createdBy: string;
  readonly staffFeedback: ScientificReturnAgentFeedback | null;
  readonly feedbackComment: string | null;
  readonly feedbackBy: string | null;
  readonly feedbackAt: string | null;
}

export type ScientificReturnCandidatesPage = Page<ScientificReturnCandidate>;
export type ScientificReturnRunsPage = Page<ScientificReturnRun>;
export type ScientificReturnReviewQueuePage = Page<ScientificReturnReviewItem>;

export type InvestigationObjective = 'DISCOVER_CANDIDATE' | 'ENRICH_CANDIDATE';

export type InvestigationStatus =
  | 'CREATED'
  | 'OBSERVING'
  | 'PLANNING'
  | 'VALIDATING'
  | 'EXECUTING'
  | 'REFLECTING'
  | 'AWAITING_HUMAN_REVIEW'
  | 'STOPPED'
  | 'FAILED';

export type InvestigationMode = 'DISABLED' | 'SHADOW' | 'POLICY_ONLY' | 'SUPERVISED' | 'SCHEDULED';

export type IterationStatus = 'RUNNING' | 'COMPLETED' | 'FAILED';

export type InvestigationStopReason =
  | 'EVIDENCE_SUFFICIENT'
  | 'NO_RESULTS'
  | 'NO_EVIDENCE_ADDED'
  | 'NO_PROGRESS'
  | 'ACTION_REJECTED'
  | 'QUERY_REPEATED'
  | 'BUDGET_EXHAUSTED'
  | 'ITERATION_LIMIT_REACHED'
  | 'CANDIDATE_LIMIT_REACHED'
  | 'REASONER_UNAVAILABLE'
  | 'INVALID_PLAN'
  | 'TOOL_UNAVAILABLE'
  | 'TOOL_FAILED'
  | 'CANDIDATE_ALREADY_DECIDED'
  | 'PRESENTED_FOR_REVIEW'
  | 'INSUFFICIENT_EVIDENCE';

export interface InvestigationObservation {
  readonly researcher: string;
  readonly projectReference: string;
  readonly objects: readonly Record<string, string>[];
  readonly triedQueries: readonly string[];
  readonly allowedActions: readonly string[];
}

export interface InvestigationPlan {
  readonly objective: string;
  readonly actionType: ScientificReturnAgentAction;
  readonly objectId: string | null;
  readonly reasoningSummary: string;
  readonly expectedEvidence: readonly ScientificReturnEvidenceType[];
}

export interface InvestigationPolicy {
  readonly authorized: boolean;
  readonly justification: string;
  readonly rejectionReason: string | null;
}

export interface InvestigationTool {
  readonly executedQueries: readonly string[];
  readonly sources: readonly string[];
  readonly totalResults: number;
  readonly createdCandidateIds: readonly string[];
  readonly addedEvidenceIds: readonly string[];
}

export interface InvestigationDelta {
  readonly added: readonly ScientificReturnEvidenceType[];
  readonly preserved: readonly ScientificReturnEvidenceType[];
  readonly removed: readonly ScientificReturnEvidenceType[];
}

export interface InvestigationReflection {
  readonly progress: string;
  readonly evidenceDeltaSummary: string;
  readonly remainingGaps: readonly string[];
  readonly recommendedStop: boolean;
  readonly reasoningSummary: string;
}

export interface InvestigationIteration {
  readonly id: string;
  readonly number: number;
  readonly status: IterationStatus;
  readonly startedAt: string;
  readonly completedAt: string | null;
  readonly observation: InvestigationObservation | null;
  readonly plan: InvestigationPlan | null;
  readonly policy: InvestigationPolicy | null;
  readonly tool: InvestigationTool | null;
  readonly evidenceDelta: InvestigationDelta | null;
  readonly reflection: InvestigationReflection | null;
  readonly evidenceBeforeHash: string | null;
  readonly evidenceAfterHash: string | null;
  readonly errorMessage: string | null;
}

export interface InvestigationBudget {
  readonly maxIterations: number;
  readonly maxQueries: number;
  readonly maxNewCandidates: number;
  readonly usedIterations: number;
  readonly usedQueries: number;
  readonly createdCandidates: number;
}

export interface ScientificReturnInvestigation {
  readonly id: string;
  readonly watchId: string;
  readonly candidateId: string | null;
  readonly objective: InvestigationObjective;
  readonly status: InvestigationStatus;
  readonly mode: InvestigationMode;
  readonly stopReason: InvestigationStopReason | null;
  readonly currentIteration: number;
  readonly budget: InvestigationBudget;
  readonly startedAt: string;
  readonly completedAt: string | null;
  readonly createdBy: string;
  readonly previousInvestigationId: string | null;
  readonly iterations: readonly InvestigationIteration[];
}

export type FullAgenticStatus =
  | 'QUEUED'
  | 'RUNNING'
  | 'CANCEL_REQUESTED'
  | 'COMPLETED'
  | 'FAILED'
  | 'CANCELLED';

export interface FullAgenticInvestigation {
  readonly id: string;
  readonly watchId: string;
  readonly objective: InvestigationObjective;
  readonly candidateId: string | null;
  readonly searchRunId: string | null;
  readonly status: FullAgenticStatus;
  readonly budget: Readonly<Record<string, number>>;
  readonly usage: Readonly<Record<string, number>>;
  readonly createdBy: string;
  readonly createdAt: string;
  readonly startedAt: string | null;
  readonly completedAt: string | null;
  readonly heartbeatAt: string | null;
  readonly failureReason: string | null;
  readonly degradedReason?: string | null;
}

export interface AgenticTrajectoryEvent {
  readonly id: string;
  readonly sequence: number;
  readonly kind: string;
  readonly payload: Readonly<Record<string, unknown>>;
  readonly occurredAt: string;
}

export type ScientificReturnKnowledgeKind = 'INVENTORY_VARIATION_EXAMPLE' | 'CURATORIAL_LESSON';
export type ScientificReturnKnowledgeStatus = 'PROPOSED' | 'ACTIVE' | 'RETIRED';

export interface ScientificReturnKnowledgeItem {
  readonly id: string;
  readonly institutionId: string | null;
  readonly kind: ScientificReturnKnowledgeKind;
  readonly status: ScientificReturnKnowledgeStatus;
  readonly content: string;
  readonly registeredNumber: string | null;
  readonly observedForm: string | null;
  readonly supersedesId: string | null;
  readonly sourceCandidateId: string | null;
  readonly sourceDecisionId: string | null;
  readonly createdBy: string;
  readonly createdAt: string;
  readonly validatedBy: string | null;
  readonly validatedAt: string | null;
  readonly retiredBy: string | null;
  readonly retiredAt: string | null;
}
