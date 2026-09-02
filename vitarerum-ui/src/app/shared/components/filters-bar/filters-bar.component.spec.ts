import { ChangeDetectionStrategy, Component, signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';

import {
  FiltersBarComponent,
  FiltersBarSelect,
  FiltersBarSelectChange,
} from './filters-bar.component';

const SELECTS: readonly FiltersBarSelect[] = [
  {
    key: 'status',
    label: 'Status',
    value: 'ACTIVE',
    options: [
      { value: '', label: 'All statuses' },
      { value: 'ACTIVE', label: 'Active' },
    ],
  },
];

@Component({
  standalone: true,
  imports: [FiltersBarComponent],
  template: `<app-filters-bar
    [count]="count()"
    itemSingular="item"
    itemPlural="items"
    [selects]="selects"
    searchLabel="Search"
    [canClear]="canClear()"
    (selectChanged)="selectChanges.push($event)"
    (searchChanged)="searches.push($event)"
    (cleared)="cleared = cleared + 1"
  />`,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
class HostComponent {
  readonly count = signal(3);
  readonly canClear = signal(true);
  readonly selects = SELECTS;
  readonly selectChanges: FiltersBarSelectChange[] = [];
  readonly searches: (string | null)[] = [];
  cleared = 0;
}

describe('FiltersBarComponent', () => {
  let fixture: ComponentFixture<HostComponent>;
  let host: HostComponent;
  let root: HTMLElement;

  beforeEach(async () => {
    vi.useFakeTimers();
    await TestBed.configureTestingModule({ imports: [HostComponent] }).compileComponents();
    fixture = TestBed.createComponent(HostComponent);
    host = fixture.componentInstance;
    root = fixture.nativeElement as HTMLElement;
    fixture.detectChanges();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('pluralises the count and preselects each filter value', () => {
    expect(root.querySelector('.filters-bar__count')?.textContent?.trim()).toBe('3');
    expect(root.textContent).toContain('items');
    expect(root.querySelector<HTMLSelectElement>('select')?.value).toBe('ACTIVE');

    host.count.set(1);
    fixture.detectChanges();
    expect(root.textContent).toContain('item');
  });

  it('emits a select change immediately, with no submit step', () => {
    const select = root.querySelector<HTMLSelectElement>('select')!;
    select.value = '';
    select.dispatchEvent(new Event('change'));

    expect(host.selectChanges).toEqual([{ key: 'status', value: '' }]);
  });

  it('collapses a burst of typing into one search', () => {
    const input = root.querySelector<HTMLInputElement>('input[type="search"]')!;

    for (const term of ['h', 'he', 'her', 'herb']) {
      input.value = term;
      input.dispatchEvent(new Event('input'));
      vi.advanceTimersByTime(50);
    }
    expect(host.searches).toEqual([]);

    vi.advanceTimersByTime(300);
    expect(host.searches).toEqual(['herb']);
  });

  it('searches at once on Enter and does not repeat it when the debounce lands', () => {
    const input = root.querySelector<HTMLInputElement>('input[type="search"]')!;
    input.value = 'herb';
    input.dispatchEvent(new Event('input'));
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));

    expect(host.searches).toEqual(['herb']);

    vi.advanceTimersByTime(400);
    expect(host.searches).toEqual(['herb']);
  });

  it('reports a blank search as no filter at all', () => {
    const input = root.querySelector<HTMLInputElement>('input[type="search"]')!;
    input.value = '   ';
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));

    expect(host.searches).toEqual([]);
  });

  it('offers the reset action only while a filter is set', () => {
    root.querySelector<HTMLButtonElement>('.filters-bar__clear')!.click();
    expect(host.cleared).toBe(1);

    host.canClear.set(false);
    fixture.detectChanges();
    expect(root.querySelector('.filters-bar__clear')).toBeNull();
  });
});
