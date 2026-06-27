export type UseType = 'EXHIBITION' | 'IN_SITU_VISIT' | 'OTHER';

// The backend wraps the use type in a value object: `intendedUse: { useType,
// description }`. The app reads the flat `useType`; `description` is currently
// unused but kept for fidelity with the contract.
export interface IntendedUse {
  readonly useType: UseType;
  readonly description: string;
}

export type ProposalStatus = 'SUBMITTED' | 'PENDING' | 'APPROVED' | 'REJECTED' | 'CANCELLED';

export type ProposalEventType =
  | 'SUBMITTED'
  | 'ASSIGNED'
  | 'FORWARDED'
  | 'INTENDED_USE_UPDATED'
  | 'DOCUMENTS_REQUESTED'
  | 'DOCUMENTS_SUBMITTED'
  | 'REVIEW_STARTED'
  | 'REFERRED_TO_DIRECTION'
  | 'DIRECTION_CLARIFIED'
  | 'APPROVED'
  | 'REJECTED'
  | 'CANCELLED';

export type UseStatus = 'CREATED' | 'IN_PROGRESS' | 'COMPLETED' | 'CANCELLED';

export type UseResult = 'COMPLETED' | 'CANCELLED';

export type UseEventType = 'REQUESTED' | 'STARTED' | 'COMPLETED' | 'CANCELLED';

export type MediaType = 'DOCUMENT' | 'IMAGE' | 'VIDEO' | 'OTHER';

export type StatusTone = 'approved' | 'cancelled' | 'pending' | 'rejected' | 'review' | 'submitted';

export interface StatusPresentation {
  readonly label: string;
  readonly tone: StatusTone;
}

const PROPOSAL_STATUS_PRESENTATION = {
  SUBMITTED: { label: 'Submitted', tone: 'submitted' },
  PENDING: { label: 'Under review', tone: 'review' },
  APPROVED: { label: 'Approved', tone: 'approved' },
  REJECTED: { label: 'Rejected', tone: 'rejected' },
  CANCELLED: { label: 'Cancelled', tone: 'cancelled' },
} as const satisfies Record<ProposalStatus, StatusPresentation>;

const USE_STATUS_PRESENTATION = {
  CREATED: { label: 'Created', tone: 'submitted' },
  IN_PROGRESS: { label: 'In progress', tone: 'review' },
  COMPLETED: { label: 'Completed', tone: 'approved' },
  CANCELLED: { label: 'Cancelled', tone: 'cancelled' },
} as const satisfies Record<UseStatus, StatusPresentation>;

export function getProposalStatusPresentation(status: ProposalStatus): StatusPresentation {
  return PROPOSAL_STATUS_PRESENTATION[status];
}

export function getUseStatusPresentation(status: UseStatus): StatusPresentation {
  return USE_STATUS_PRESENTATION[status];
}
