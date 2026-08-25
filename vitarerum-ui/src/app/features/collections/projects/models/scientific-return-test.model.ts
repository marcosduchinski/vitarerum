export type TestSourceKind = 'TEXT_DOCUMENT' | 'BIBLIOGRAPHIC_REFERENCE';
export type TestSourceStatus = 'ACTIVE' | 'RETIRED';
export type TestBatchStatus =
  | 'DRAFT'
  | 'QUEUED'
  | 'RUNNING'
  | 'CANCELLING'
  | 'COMPLETED'
  | 'COMPLETED_WITH_ERRORS'
  | 'FAILED'
  | 'CANCELLED';
export type TestItemStatus = 'PENDING' | 'RUNNING' | 'COMPLETED' | 'ERROR' | 'CANCELLED';

export interface TestSourceRevision {
  readonly id: string;
  readonly revision: number;
  readonly locator: string | null;
  readonly authors: readonly string[];
  readonly content: string;
  readonly contentHash: string;
  readonly createdAt: string;
}

export interface TestSource {
  readonly id: string;
  readonly name: string;
  readonly kind: TestSourceKind;
  readonly status: TestSourceStatus;
  readonly currentRevision: number;
  readonly contentHash: string;
  readonly createdAt: string;
  readonly updatedAt: string;
  readonly revisions?: readonly TestSourceRevision[];
}

export interface TestSourceWrite {
  readonly name: string;
  readonly kind: TestSourceKind;
  readonly content: string;
  readonly locator: string | null;
  readonly authors: readonly string[];
}

export interface TestItem {
  readonly id: string;
  readonly ordinal: number;
  readonly author: string;
  readonly objectName: string;
  readonly inventoryNumber: string;
  readonly status: TestItemStatus;
  readonly attemptNumber: number;
  readonly errorCode: string | null;
  readonly errorMessage: string | null;
  readonly startedAt: string | null;
  readonly completedAt: string | null;
}

export interface TestBatchProgress {
  readonly total: number;
  readonly pending: number;
  readonly running: number;
  readonly completed: number;
  readonly error: number;
  readonly cancelled: number;
  readonly percentage: number;
}

export interface TestBatch {
  readonly id: string;
  readonly name: string | null;
  readonly description: string | null;
  readonly status: TestBatchStatus;
  readonly createdAt: string;
  readonly startedAt: string | null;
  readonly completedAt: string | null;
  readonly sourceIds: readonly string[];
  readonly items: readonly TestItem[];
  readonly progress: TestBatchProgress;
}

export interface TestCandidate {
  readonly id: string;
  readonly itemId: string;
  readonly attemptNumber: number;
  readonly author: string;
  readonly objectName: string;
  readonly inventoryNumber: string;
  readonly rank: number;
  readonly score: string;
  readonly scoreVersion: string;
  readonly sourceId: string;
  readonly sourceName: string;
  readonly sourceRevision: number;
  readonly sourceLocator: string | null;
  readonly query: string;
  readonly discoveryBasis: string;
  readonly inventoryEvidenceStatus: 'VERIFIED' | 'NOT_OBSERVED' | 'UNAVAILABLE';
  readonly evidence: string | null;
}

export interface TestReadiness {
  readonly enabled: boolean;
  readonly configurationValid: boolean;
  readonly message: string | null;
}
