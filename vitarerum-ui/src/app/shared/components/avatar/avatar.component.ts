import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

import { GroupName } from '@core/auth/models/group-name.enum';
import { getRolePresentation } from '@shared/components/role-chip/role-chip.component';

/**
 * Initials medallion for a person. Decorative (the adjacent name carries the
 * accessible text), optionally tinted by a role so identity is scannable at a
 * glance across the admin tables.
 */
@Component({
  selector: 'app-avatar',
  standalone: true,
  template: `<span class="avatar" [class]="toneClass()" aria-hidden="true">{{
    initials()
  }}</span>`,
  styleUrl: './avatar.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AvatarComponent {
  readonly name = input.required<string>();
  readonly group = input<GroupName>();

  protected readonly initials = computed(() => {
    const parts = this.name().trim().split(/\s+/).filter(Boolean);
    if (!parts.length) return '?';
    const first = parts[0][0];
    const last = parts.length > 1 ? parts[parts.length - 1][0] : '';
    return (first + last).toUpperCase();
  });

  protected readonly toneClass = computed(() => {
    const group = this.group();
    return `avatar--${group ? getRolePresentation(group).tone : 'neutral'}`;
  });
}
