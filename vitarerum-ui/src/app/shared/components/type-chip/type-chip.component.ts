import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

import { UseType } from '@shared/models/collection-use-status.model';

interface TypePresentation {
  label: string;
  tone: 'exhibition' | 'other' | 'research';
}

const TYPE_PRESENTATION = {
  EXHIBITION: { label: 'Exhibition', tone: 'exhibition' },
  IN_SITU_VISIT: { label: 'In-situ visit', tone: 'research' },
  OTHER: { label: 'Other', tone: 'other' },
} as const satisfies Record<UseType, TypePresentation>;

export function getUseTypePresentation(type: UseType | null | undefined): TypePresentation {
  return type ? TYPE_PRESENTATION[type] : TYPE_PRESENTATION.OTHER;
}

@Component({
  selector: 'app-type-chip',
  standalone: true,
  templateUrl: './type-chip.component.html',
  styleUrl: './type-chip.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class TypeChipComponent {
  readonly type = input.required<UseType | null | undefined>();
  readonly context = input<'Proposal' | 'Project'>('Proposal');

  protected readonly presentation = computed(() => getUseTypePresentation(this.type()));
  protected readonly chipClass = computed(() => `type-chip type-chip--${this.presentation().tone}`);
  protected readonly ariaLabel = computed(
    () => `${this.context()} type: ${this.presentation().label}`,
  );
}
