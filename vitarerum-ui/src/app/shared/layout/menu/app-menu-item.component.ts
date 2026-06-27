import { ChangeDetectionStrategy, Component, computed, input, signal } from '@angular/core';
import { RouterLink, RouterLinkActive } from '@angular/router';

import { MenuNode } from './menu.model';

@Component({
  selector: 'app-menu-item',
  standalone: true,
  imports: [RouterLink, RouterLinkActive],
  templateUrl: './app-menu-item.component.html',
  styleUrl: './app-menu-item.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AppMenuItemComponent {
  readonly item = input.required<MenuNode>();
  readonly depth = input(0);

  protected readonly expanded = signal(false);
  protected readonly isRoot = computed(() => this.depth() === 0);
  protected readonly visible = computed(() => this.item().visible !== false);
  protected readonly hasChildren = computed(() => (this.item().items?.length ?? 0) > 0);
  protected readonly showChildren = computed(
    () => this.hasChildren() && (this.isRoot() || this.expanded()),
  );
  protected readonly submenuId = computed(
    () =>
      `submenu-${this.depth()}-${this.item().label.toLowerCase().replace(/\W+/g, '-')}`,
  );
  protected readonly iconClass = computed(() =>
    ['layout-menuitem-icon', this.item().icon].filter(Boolean).join(' '),
  );

  protected toggle(event: Event): void {
    if (this.item().disabled) {
      event.preventDefault();
      return;
    }
    if (this.hasChildren()) {
      this.expanded.update(v => !v);
    }
  }
}
