import {
  ChangeDetectionStrategy,
  Component,
  input,
  ViewEncapsulation,
} from '@angular/core';

/**
 * Shared ledger-style admin table. Renders the `<table>` and projects the
 * consumer's `<thead>`/`<tbody>`. Unencapsulated so the (global) styling below
 * reaches the projected rows. Helper classes for cells:
 *   .data-table__link     — accent link (names)
 *   .data-table__muted    — secondary text
 *   .data-table__num      — tabular numerals (ids, counts, phones)
 *   .data-table__actions  — right-aligned action cell
 *   .is-secondary         — column hidden on narrow viewports
 */
@Component({
  selector: 'app-data-table',
  standalone: true,
  template: `<table class="data-table" [attr.aria-label]="ariaLabel()">
    <ng-content />
  </table>`,
  styleUrl: './data-table.component.scss',
  encapsulation: ViewEncapsulation.None,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class DataTableComponent {
  readonly ariaLabel = input.required<string>();
}
