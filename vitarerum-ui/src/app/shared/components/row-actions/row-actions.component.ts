import { ChangeDetectionStrategy, Component, input, signal } from '@angular/core';
import { MenuItem } from 'primeng/api';
import { Menu } from 'primeng/menu';

/**
 * Kebab ("more actions") control for table/card rows.
 *
 * Renders an ellipsis trigger and a PrimeNG popup menu, tracking its own
 * open state so a list can drop one instance per row without juggling a
 * shared "which menu is open" signal.
 */
@Component({
  selector: 'app-row-actions',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Menu],
  templateUrl: './row-actions.component.html',
  styleUrl: './row-actions.component.scss',
})
export class RowActionsComponent {
  readonly items = input.required<MenuItem[]>();
  readonly disabled = input(false);
  readonly ariaLabel = input('Row actions');

  protected readonly open = signal(false);
}
