import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

import { GroupName } from '@core/auth/models/group-name.enum';

interface RolePresentation {
  label: string;
  tone: 'external' | 'curatorial' | 'collections' | 'direction' | 'admin';
}

const ROLE_PRESENTATION = {
  EXTERNAL: { label: 'External researcher', tone: 'external' },
  CURATORIAL: { label: 'Curatorial', tone: 'curatorial' },
  COLLECTIONS_MANAGEMENT: { label: 'Collections management', tone: 'collections' },
  DIRECTION: { label: 'Direction', tone: 'direction' },
  SYS_ADMIN: { label: 'Administrator', tone: 'admin' },
} as const satisfies Record<GroupName, RolePresentation>;

export function getRolePresentation(group: GroupName): RolePresentation {
  // Defensive: never crash the host view if an unexpected value slips through
  // (e.g. a backend that sends a group shape the caller didn't normalise).
  return ROLE_PRESENTATION[group] ?? { label: group ?? '', tone: 'external' };
}

@Component({
  selector: 'app-role-chip',
  standalone: true,
  templateUrl: './role-chip.component.html',
  styleUrl: './role-chip.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class RoleChipComponent {
  readonly group = input.required<GroupName>();

  protected readonly presentation = computed(() => getRolePresentation(this.group()));
  protected readonly chipClass = computed(
    () => `role-chip role-chip--${this.presentation().tone}`,
  );
  protected readonly ariaLabel = computed(() => `Group: ${this.presentation().label}`);
}
