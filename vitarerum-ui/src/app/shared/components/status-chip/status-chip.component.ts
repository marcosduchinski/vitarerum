import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

export type WorkflowStatusKind = 'proposal' | 'project';

export type WorkflowStatus =
  | 'SUBMITTED'
  | 'PENDING'
  | 'APPROVED'
  | 'REJECTED'
  | 'CANCELLED'
  | 'CREATED'
  | 'IN_PROGRESS'
  | 'COMPLETED';

interface StatusPresentation {
  label: string;
  tone: 'approved' | 'cancelled' | 'pending' | 'rejected' | 'review' | 'submitted';
}

const STATUS_PRESENTATION = {
  SUBMITTED: { label: 'Submitted', tone: 'submitted' },
  PENDING: { label: 'Under review', tone: 'review' },
  APPROVED: { label: 'Approved', tone: 'approved' },
  REJECTED: { label: 'Rejected', tone: 'rejected' },
  CANCELLED: { label: 'Cancelled', tone: 'cancelled' },
  CREATED: { label: 'Created', tone: 'submitted' },
  IN_PROGRESS: { label: 'In progress', tone: 'review' },
  COMPLETED: { label: 'Completed', tone: 'approved' },
} as const satisfies Record<WorkflowStatus, StatusPresentation>;

export function getWorkflowStatusPresentation(status: WorkflowStatus): StatusPresentation {
  return STATUS_PRESENTATION[status];
}

@Component({
  selector: 'app-status-chip',
  standalone: true,
  templateUrl: './status-chip.component.html',
  styleUrl: './status-chip.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class StatusChipComponent {
  readonly kind = input.required<WorkflowStatusKind>();
  readonly status = input.required<WorkflowStatus>();

  protected readonly presentation = computed(() => getWorkflowStatusPresentation(this.status()));
  protected readonly chipClass = computed(() => `status-chip status-chip--${this.presentation().tone}`);
  protected readonly ariaLabel = computed(
    () => `${this.kind() === 'proposal' ? 'Proposal' : 'Project'} status: ${this.presentation().label}`,
  );
}
