import { ChangeDetectionStrategy, Component, input } from '@angular/core';

import {
  StatusChipComponent,
  WorkflowStatus,
} from '@shared/components/status-chip/status-chip.component';
import {
  getUseTypePresentation,
  TypeChipComponent,
} from '@shared/components/type-chip/type-chip.component';

import { ProposalDetail } from '../../models/proposal.model';
import {
  formatProposalDetailDateTime,
  PROPOSAL_DETAIL_GROUP_LABELS,
} from '../../proposal-detail.presentation';

@Component({
  selector: 'app-proposal-overview-section',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [StatusChipComponent, TypeChipComponent],
  templateUrl: './proposal-overview-section.component.html',
  styleUrl: './proposal-overview-section.component.scss',
})
export class ProposalOverviewSectionComponent {
  readonly proposal = input.required<ProposalDetail>();

  protected readonly formatDateTime = formatProposalDetailDateTime;

  protected asWorkflowStatus(value: string): WorkflowStatus {
    return value as WorkflowStatus;
  }

  protected typeLabel(): string {
    return getUseTypePresentation(this.proposal().type).label;
  }

  protected requesterGroupLabel(): string {
    return PROPOSAL_DETAIL_GROUP_LABELS[this.proposal().requestedBy.group];
  }

  protected assigneeGroupLabel(): string {
    const assignee = this.proposal().assignedTo;
    return assignee ? PROPOSAL_DETAIL_GROUP_LABELS[assignee.group] : 'No staff group';
  }

  protected submissionChannelLabel(): string {
    return this.proposal().submissionChannel === 'PUBLIC' ? 'Public form' : 'Signed-in request';
  }

  protected requestedPeriod(): string {
    const proposal = this.proposal();

    if (!proposal.beginDate && !proposal.endDate) {
      return 'Not set';
    }

    if (proposal.beginDate && proposal.endDate) {
      return `${this.formatDate(proposal.beginDate)} to ${this.formatDate(proposal.endDate)}`;
    }

    return proposal.beginDate
      ? `From ${this.formatDate(proposal.beginDate)}`
      : `Until ${this.formatDate(proposal.endDate!)}`;
  }

  protected formatDate(value: string): string {
    try {
      return new Date(`${value}T00:00:00`).toLocaleDateString('en-GB', {
        day: '2-digit',
        month: 'short',
        year: 'numeric',
      });
    } catch {
      return value;
    }
  }

  protected pendingCorrectionsCount(): number {
    return (this.proposal().correctionItems ?? []).filter((item) => item.status === 'REQUESTED')
      .length;
  }
}
