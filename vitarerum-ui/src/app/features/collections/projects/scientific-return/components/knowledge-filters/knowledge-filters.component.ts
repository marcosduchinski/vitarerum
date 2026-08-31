import { ChangeDetectionStrategy, Component, computed, input, output } from '@angular/core';

import {
  ScientificReturnKnowledgeKind,
  ScientificReturnKnowledgeStatus,
} from '../../../models/scientific-return.model';

export interface KnowledgeFilterChange {
  readonly status: ScientificReturnKnowledgeStatus | null;
  readonly kind: ScientificReturnKnowledgeKind | null;
  readonly inventoryNumber: string | null;
}

@Component({
  selector: 'app-knowledge-filters',
  standalone: true,
  templateUrl: './knowledge-filters.component.html',
  styleUrl: './knowledge-filters.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class KnowledgeFiltersComponent {
  readonly status = input<ScientificReturnKnowledgeStatus | null>(null);
  readonly kind = input<ScientificReturnKnowledgeKind | null>(null);
  readonly inventoryNumber = input<string | null>(null);
  readonly changed = output<KnowledgeFilterChange>();
  protected readonly hasFilters = computed(
    () => this.status() !== null || this.kind() !== null || this.inventoryNumber() !== null,
  );

  protected apply(status: string, kind: string, inventoryNumber: string): void {
    this.changed.emit({
      status: (status || null) as ScientificReturnKnowledgeStatus | null,
      kind: (kind || null) as ScientificReturnKnowledgeKind | null,
      inventoryNumber: inventoryNumber.trim() || null,
    });
  }

  protected clearStatus(): void {
    this.emitCurrent({ status: null });
  }

  protected clearKind(): void {
    this.emitCurrent({ kind: null });
  }

  protected clearInventoryNumber(): void {
    this.emitCurrent({ inventoryNumber: null });
  }

  protected clearAll(): void {
    this.changed.emit({ status: null, kind: null, inventoryNumber: null });
  }

  protected statusLabel(): string {
    if (this.status() === 'PROPOSED') return 'Awaiting validation';
    if (this.status() === 'RETIRED') return 'Retired';
    return 'Active';
  }

  protected kindLabel(): string {
    return this.kind() === 'CURATORIAL_LESSON' ? 'Curatorial lesson' : 'Inventory example';
  }

  private emitCurrent(overrides: Partial<KnowledgeFilterChange>): void {
    this.changed.emit({
      status: this.status(),
      kind: this.kind(),
      inventoryNumber: this.inventoryNumber(),
      ...overrides,
    });
  }
}
