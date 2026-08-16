import { Page } from '@shared/models/page.model';

export type ScientificReturnWatchStatus = 'ACTIVE' | 'PAUSED' | 'CLOSED';
export type ScientificReturnRunStatus = 'RUNNING' | 'COMPLETED' | 'FAILED';
export type ScientificReturnQueryStatus = 'COMPLETED' | 'FAILED';
export type ScientificReturnCandidateStatus = 'PENDING' | 'CONFIRMED' | 'DISMISSED' | 'SNOOZED';
export type ScientificReturnDecision = 'CONFIRM' | 'CORRECT_AND_CONFIRM' | 'DISMISS' | 'SNOOZE';
export type ScientificReturnEvidenceStrength = 'PRIMARY' | 'SUPPORTING' | 'WEAK';
export type ScientificReturnAgentAnalysisStatus = 'RUNNING' | 'COMPLETED' | 'FAILED';
export type ScientificReturnAgentConfidence = 'LOW' | 'MEDIUM' | 'HIGH';
export type ScientificReturnAgentFeedback = 'USEFUL' | 'PARTIALLY_USEFUL' | 'NOT_USEFUL';
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
  readonly projectSnapshotId: string;
}

export interface ScientificReturnQuery {
  readonly id: string;
  readonly source: string;
  readonly queryText: string;
  readonly queryType: 'INVENTORY' | 'AUTHOR_INVENTORY' | 'INVENTORY_OBJECT' | 'AUTHOR_OBJECT';
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
  readonly snoozedUntil: string | null;
  readonly confirmedPublicationEntryId: string | null;
  readonly firstSeenAt: string;
  readonly evidences: readonly ScientificReturnEvidence[];
}

export interface ScientificReturnReviewItem extends ScientificReturnCandidate {
  readonly projectId: string;
}

export interface ScientificReturnMetrics {
  readonly activeWatches: number;
  readonly runs: number;
  readonly failedRuns: number;
  readonly pendingCandidates: number;
  readonly confirmedCandidates: number;
  readonly dismissedCandidates: number;
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
  readonly snoozedUntil?: string | null;
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
  readonly mode: 'SHADOW';
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
