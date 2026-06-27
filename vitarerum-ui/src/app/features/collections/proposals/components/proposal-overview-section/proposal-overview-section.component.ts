import { ChangeDetectionStrategy, Component, input } from '@angular/core';

import {
  StatusChipComponent,
  WorkflowStatus,
} from '@shared/components/status-chip/status-chip.component';

import { ProposalDetail } from '../../models/proposal.model';
import { formatProposalDetailDateTime } from '../../proposal-detail.presentation';

@Component({
  selector: 'app-proposal-overview-section',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [StatusChipComponent],
  templateUrl: './proposal-overview-section.component.html',
  styleUrl: './proposal-overview-section.component.scss',
})
export class ProposalOverviewSectionComponent {
  readonly proposal = input.required<ProposalDetail>();

  protected readonly formatDateTime = formatProposalDetailDateTime;

  protected asWorkflowStatus(value: string): WorkflowStatus {
    return value as WorkflowStatus;
  }
}
