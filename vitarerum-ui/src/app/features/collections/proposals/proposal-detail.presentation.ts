import { GroupName } from '@core/auth/models/group-name.enum';

// A selectable staff member (label + permission id), used by the proposal
// assignment/forward controls.
export interface StaffOption {
  readonly label: string;
  readonly permissionId: string;
}

export const PROPOSAL_DETAIL_GROUP_LABELS: Record<GroupName, string> = {
  EXTERNAL: 'External',
  COLLECTIONS_MANAGEMENT: 'Collections management',
  CURATORIAL: 'Curatorial',
  DIRECTION: 'Direction',
  SYS_ADMIN: 'Administration',
};

export function formatProposalDetailDateTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString('en-GB', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return iso;
  }
}
