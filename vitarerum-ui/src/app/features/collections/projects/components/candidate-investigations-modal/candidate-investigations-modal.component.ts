import { formatDate } from '@angular/common';
import { ChangeDetectionStrategy, Component, input, output } from '@angular/core';

import { ModalPanelComponent } from '@shared/components/modal-panel/modal-panel.component';

import { ScientificReturnInvestigation } from '../../models/scientific-return.model';
import {
  AgentExecutionCardComponent,
  AgentExecutionMetadata,
} from '../agent-execution-card/agent-execution-card.component';
import {
  budgetLabel,
  InvestigationTimelineComponent,
  stopReasonLabel,
} from '../investigation-timeline/investigation-timeline.component';

@Component({
  selector: 'app-candidate-investigations-modal',
  standalone: true,
  imports: [AgentExecutionCardComponent, InvestigationTimelineComponent, ModalPanelComponent],
  templateUrl: './candidate-investigations-modal.component.html',
  styleUrl: './candidate-investigations-modal.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CandidateInvestigationsModalComponent {
  readonly open = input(false);
  readonly candidateTitle = input('');
  readonly investigations = input<readonly ScientificReturnInvestigation[]>([]);
  readonly loading = input(false);
  readonly error = input<string | null>(null);

  readonly closed = output<void>();

  protected investigationTitle(investigation: ScientificReturnInvestigation): string {
    return investigation.objective === 'DISCOVER_CANDIDATE' ? 'Discovery' : 'Enrichment';
  }

  protected investigationMetadata(
    investigation: ScientificReturnInvestigation,
  ): readonly AgentExecutionMetadata[] {
    return [
      { label: 'Outcome', value: stopReasonLabel(investigation) },
      { label: 'Mode', value: investigation.mode.toLowerCase() },
      { label: 'Budget used', value: budgetLabel(investigation) },
      { label: 'Started', value: formatDate(investigation.startedAt, 'short', 'en-GB') },
    ];
  }
}
