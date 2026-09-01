import { ChangeDetectionStrategy, Component, input, output } from '@angular/core';

import { ModalPanelComponent } from '@shared/components/modal-panel/modal-panel.component';

import { ScientificReturnInvestigation } from '../../models/scientific-return.model';
import { InvestigationTimelineComponent } from '../investigation-timeline/investigation-timeline.component';

@Component({
  selector: 'app-candidate-investigations-modal',
  standalone: true,
  imports: [InvestigationTimelineComponent, ModalPanelComponent],
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
}
