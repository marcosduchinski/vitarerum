import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, input, output } from '@angular/core';

import { ModalPanelComponent } from '@shared/components/modal-panel/modal-panel.component';

import {
  CandidateAgentAnalysis,
  ScientificReturnAgentFeedback,
} from '../../models/scientific-return.model';

export interface AgentAnalysisFeedback {
  readonly analysisId: string;
  readonly value: ScientificReturnAgentFeedback;
}

@Component({
  selector: 'app-candidate-analyses-modal',
  standalone: true,
  imports: [DatePipe, ModalPanelComponent],
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

  protected rate(analysisId: string, value: ScientificReturnAgentFeedback): void {
    this.feedbackGiven.emit({ analysisId, value });
  }
}
