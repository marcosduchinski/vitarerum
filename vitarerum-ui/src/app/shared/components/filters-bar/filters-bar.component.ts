import { ChangeDetectionStrategy, Component, input, output } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Subject, debounceTime } from 'rxjs';

export interface FiltersBarOption {
  readonly value: string;
  readonly label: string;
}

export interface FiltersBarSelect {
  /** Identifies the select in the `selectChanged` output. */
  readonly key: string;
  readonly label: string;
  readonly value: string;
  readonly options: readonly FiltersBarOption[];
}

export interface FiltersBarSelectChange {
  readonly key: string;
  readonly value: string;
}

/** Typing settles before the page reloads, so a search costs one request. */
const SEARCH_DEBOUNCE_MS = 300;

/**
 * The filter bar every listing page shares: a count on the left, an optional
 * search box and the selects on the right, and a reset action.
 *
 * Filters apply on change — no submit button — so the three pages that use it
 * behave alike. The controls are rendered here rather than projected so that
 * one stylesheet governs their appearance.
 */
@Component({
  selector: 'app-filters-bar',
  standalone: true,
  templateUrl: './filters-bar.component.html',
  styleUrl: './filters-bar.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class FiltersBarComponent {
  readonly count = input.required<number>();
  readonly itemSingular = input.required<string>();
  readonly itemPlural = input.required<string>();
  readonly selects = input<readonly FiltersBarSelect[]>([]);
  /** Renders the search box when set; its own label. */
  readonly searchLabel = input<string | null>(null);
  readonly searchPlaceholder = input('');
  readonly searchValue = input<string | null>(null);
  /** Explains the filters below the row, when they need explaining. */
  readonly hint = input<string | null>(null);
  readonly ariaLabel = input('Filters');
  readonly disabled = input(false);
  readonly canClear = input(false);

  readonly selectChanged = output<FiltersBarSelectChange>();
  readonly searchChanged = output<string | null>();
  readonly cleared = output<void>();

  private readonly typed = new Subject<string>();
  private lastSearch: string | null = null;

  constructor() {
    this.typed
      .pipe(debounceTime(SEARCH_DEBOUNCE_MS), takeUntilDestroyed())
      .subscribe((term) => this.emitSearch(term));
  }

  protected onSelect(key: string, event: Event): void {
    this.selectChanged.emit({ key, value: (event.target as HTMLSelectElement).value });
  }

  protected onSearchInput(event: Event): void {
    this.typed.next((event.target as HTMLInputElement).value);
  }

  /** Enter skips the debounce: the curator has finished typing. */
  protected onSearchEnter(event: Event): void {
    this.emitSearch((event.target as HTMLInputElement).value);
  }

  protected clear(): void {
    this.lastSearch = null;
    this.cleared.emit();
  }

  private emitSearch(term: string): void {
    const value = term.trim() || null;
    if (value === this.lastSearch) return;
    this.lastSearch = value;
    this.searchChanged.emit(value);
  }
}
