import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, input, output } from '@angular/core';

import { ScientificReturnKnowledgeItem } from '../../../models/scientific-return.model';
import { isDiscardedProposal, knowledgeStatusLabel } from '../../../utils/knowledge-status.util';

@Component({
  selector: 'app-knowledge-history',
  standalone: true,
  imports: [DatePipe],
  templateUrl: './knowledge-history.component.html',
  styleUrl: './knowledge-history.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class KnowledgeHistoryComponent {
  readonly open = input(false);
  readonly items = input<readonly ScientificReturnKnowledgeItem[]>([]);
  readonly loading = input(false);
  readonly error = input<string | null>(null);
  readonly closed = output<void>();

  protected actor(item: ScientificReturnKnowledgeItem): string {
    return item.createdByDetail?.name ?? item.createdByDetail?.email ?? item.createdBy;
  }

  protected statusLabel(item: ScientificReturnKnowledgeItem): string {
    return knowledgeStatusLabel(item).toLowerCase();
  }

  protected closingLabel(item: ScientificReturnKnowledgeItem): string {
    return isDiscardedProposal(item) ? 'Discarded' : 'Retired';
  }
}
