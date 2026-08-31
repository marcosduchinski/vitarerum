import { ChangeDetectionStrategy, Component, input, output } from '@angular/core';

import {
  ScientificReturnKnowledgeCounts,
  ScientificReturnKnowledgeStatus,
} from '../../../models/scientific-return.model';

@Component({
  selector: 'app-knowledge-summary',
  standalone: true,
  templateUrl: './knowledge-summary.component.html',
  styleUrl: './knowledge-summary.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class KnowledgeSummaryComponent {
  readonly counts = input.required<ScientificReturnKnowledgeCounts>();
  readonly selectedStatus = input<ScientificReturnKnowledgeStatus | null>(null);
  readonly statusSelected = output<ScientificReturnKnowledgeStatus>();
}
