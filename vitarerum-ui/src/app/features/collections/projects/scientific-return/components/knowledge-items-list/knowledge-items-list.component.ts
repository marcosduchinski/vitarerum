import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, input, output } from '@angular/core';
import { MenuItem } from 'primeng/api';

import { RowActionsComponent } from '@shared/components/row-actions/row-actions.component';
import { ScientificReturnKnowledgeItem } from '../../../models/scientific-return.model';
import { isDiscardedProposal, knowledgeStatusLabel } from '../../../utils/knowledge-status.util';

@Component({
  selector: 'app-knowledge-items-list',
  standalone: true,
  imports: [DatePipe, RowActionsComponent],
  templateUrl: './knowledge-items-list.component.html',
  styleUrl: './knowledge-items-list.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class KnowledgeItemsListComponent {
  readonly items = input.required<readonly ScientificReturnKnowledgeItem[]>();
  readonly canManage = input(false);
  readonly busyId = input<string | null>(null);
  readonly activate = output<ScientificReturnKnowledgeItem>();
  readonly edit = output<ScientificReturnKnowledgeItem>();
  readonly reject = output<ScientificReturnKnowledgeItem>();
  readonly retire = output<ScientificReturnKnowledgeItem>();
  readonly history = output<ScientificReturnKnowledgeItem>();

  protected actor(item: ScientificReturnKnowledgeItem): string {
    return item.createdByDetail?.name ?? item.createdByDetail?.email ?? item.createdBy;
  }

  protected typeLabel(item: ScientificReturnKnowledgeItem): string {
    return item.kind === 'INVENTORY_VARIATION_EXAMPLE' ? 'Inventory example' : 'Curatorial lesson';
  }

  protected statusLabel(item: ScientificReturnKnowledgeItem): string {
    return knowledgeStatusLabel(item);
  }

  protected closingLabel(item: ScientificReturnKnowledgeItem): string {
    return isDiscardedProposal(item) ? 'Discarded' : 'Retired';
  }

  protected actionItemsFor(item: ScientificReturnKnowledgeItem): MenuItem[] {
    return [
      {
        label: 'Edit knowledge',
        icon: 'pi pi-pencil',
        command: () => this.edit.emit(item),
      },
      {
        label: 'Retire knowledge',
        icon: 'pi pi-archive',
        command: () => this.retire.emit(item),
      },
    ];
  }
}
