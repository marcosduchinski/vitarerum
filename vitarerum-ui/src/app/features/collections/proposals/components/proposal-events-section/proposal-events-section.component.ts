import { ChangeDetectionStrategy, Component, input } from '@angular/core';

import { LoadingStateComponent } from '@shared/components/loading-state/loading-state.component';

import { ProposalEvent } from '../../models/proposal.model';
import { formatProposalDetailDateTime } from '../../proposal-detail.presentation';

@Component({
  selector: 'app-proposal-events-section',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [LoadingStateComponent],
  templateUrl: './proposal-events-section.component.html',
  styleUrl: './proposal-events-section.component.scss',
})
export class ProposalEventsSectionComponent {
  readonly events = input.required<readonly ProposalEvent[]>();
  readonly loading = input.required<boolean>();

  protected readonly formatDateTime = formatProposalDetailDateTime;
}
