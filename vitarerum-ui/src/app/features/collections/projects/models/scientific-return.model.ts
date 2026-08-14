import { Page } from '@shared/models/page.model';

export type ScientificReturnWatchStatus = 'ACTIVE' | 'PAUSED' | 'CLOSED';
export type ScientificReturnRunStatus = 'RUNNING' | 'COMPLETED' | 'FAILED';
export type ScientificReturnQueryStatus = 'COMPLETED' | 'FAILED';
export type ScientificReturnCandidateStatus = 'PENDING' | 'CONFIRMED' | 'DISMISSED' | 'SNOOZED';
export type ScientificReturnDecision = 'CONFIRM' | 'CORRECT_AND_CONFIRM' | 'DISMISS' | 'SNOOZE';
export type ScientificReturnEvidenceStrength = 'PRIMARY' | 'SUPPORTING' | 'WEAK';

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

export type ScientificReturnCandidatesPage = Page<ScientificReturnCandidate>;
export type ScientificReturnRunsPage = Page<ScientificReturnRun>;
