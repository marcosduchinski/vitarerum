import { formatDate } from '@angular/common';
import { ChangeDetectionStrategy, Component, input, output } from '@angular/core';

import { ModalPanelComponent } from '@shared/components/modal-panel/modal-panel.component';

import {
  CandidateAgentAnalysis,
  ScientificReturnAgentFeedback,
} from '../../models/scientific-return.model';
import {
  AgentExecutionCardComponent,
  AgentExecutionMetadata,
} from '../agent-execution-card/agent-execution-card.component';

export interface AgentAnalysisFeedback {
  readonly analysisId: string;
  readonly value: ScientificReturnAgentFeedback;
}

@Component({
  selector: 'app-candidate-analyses-modal',
  standalone: true,
  imports: [AgentExecutionCardComponent, ModalPanelComponent],
  templateUrl: './candidate-analyses-modal.component.html',
  styleUrl: './candidate-analyses-modal.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CandidateAnalysesModalComponent {
  readonly open = input(false);
  readonly candidateTitle = input('');
  readonly analyses = input<readonly CandidateAgentAnalysis[]>([]);
  readonly loading = input(false);
  readonly error = input<string | null>(null);
  readonly feedbackBusyId = input<string | null>(null);

  readonly closed = output<void>();
  readonly feedbackGiven = output<AgentAnalysisFeedback>();

  protected agentActionLabel(action: string): string {
    return action.toLowerCase().replaceAll('_', ' ');
  }

  protected analysisMetadata(analysis: CandidateAgentAnalysis): readonly AgentExecutionMetadata[] {
    return [
      { label: 'Model', value: analysis.model },
      { label: 'Started', value: formatDate(analysis.startedAt, 'medium', 'en-GB') },
      ...(analysis.latencyMs === null
        ? []
        : [{ label: 'Latency', value: `${analysis.latencyMs} ms` }]),
    ];
  }

  protected rate(analysisId: string, value: ScientificReturnAgentFeedback): void {
    this.feedbackGiven.emit({ analysisId, value });
  }
}
