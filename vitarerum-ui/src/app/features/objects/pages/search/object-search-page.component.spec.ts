import { ComponentFixture, TestBed } from '@angular/core/testing';
import { of } from 'rxjs';

import {
  ObjectSearchQuery,
  ObjectSearchResult,
  SearchableCollection,
} from '../../models/object-search.model';
import { OBJECT_SEARCH_SERVICE } from '../../services/object-search.service';
import { ObjectSearchPageComponent } from './object-search-page.component';

function makeResult(overrides: Partial<ObjectSearchResult> = {}): ObjectSearchResult {
  return {
    total: 1,
    page: 0,
    size: 20,
    items: [
      {
        collectionId: 'col-zoo',
        collectionName: 'Zoology',
        sourceDocumentId: 'doc-1',
        fileName: 'zoo.xlsx',
        sheet: 'Objects',
        rowNumber: 2,
        cells: { 'Inventory No': 'ZOO-1', Name: 'Jaguar' },
        highlight: '<b>Jaguar</b> found near the river',
      },
    ],
    ...overrides,
  };
}

class ServiceStub {
  result: ObjectSearchResult = makeResult();
  collections: SearchableCollection[] = [
    { id: 'col-zoo', name: 'Zoology' },
    { id: 'col-bot', name: 'Botany' },
  ];
  readonly searchCalls: ObjectSearchQuery[] = [];

  search(query: ObjectSearchQuery) {
    this.searchCalls.push(query);
    return of(this.result);
  }

  listSearchableCollections() {
    return of(this.collections);
  }
}

describe('ObjectSearchPageComponent', () => {
  let fixture: ComponentFixture<ObjectSearchPageComponent>;
  let service: ServiceStub;

  async function setup(): Promise<HTMLElement> {
    service = new ServiceStub();
    await TestBed.configureTestingModule({
      imports: [ObjectSearchPageComponent],
      providers: [{ provide: OBJECT_SEARCH_SERVICE, useValue: service }],
    }).compileComponents();

    fixture = TestBed.createComponent(ObjectSearchPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  async function typeAndSearch(el: HTMLElement, value: string): Promise<void> {
    const input = el.querySelector<HTMLInputElement>('.search-bar__input')!;
    input.value = value;
    input.dispatchEvent(new Event('input'));
    fixture.detectChanges();
    el.querySelector<HTMLButtonElement>('.search-bar__button')!.click();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
  }

  it('shows a prompt before any search is run', async () => {
    const el = await setup();
    expect(el.textContent).toContain('Search for an object');
  });

  it('renders results with the sanitised highlight after a search', async () => {
    const el = await setup();
    await typeAndSearch(el, 'jaguar');

    expect(service.searchCalls).toEqual([
      { q: 'jaguar', collectionId: undefined, page: 0, size: 20 },
    ]);
    expect(el.querySelector('.result__collection')?.textContent).toContain('Zoology');
    expect(el.querySelector('.result__highlight mark')?.textContent).toContain('Jaguar');
    expect(el.textContent).toContain('ZOO-1');
  });

  it('escapes unsafe markup in the highlight, keeping only <mark>', async () => {
    const el = await setup();
    service.result = makeResult({
      items: [
        {
          ...makeResult().items[0],
          highlight: '<img src=x onerror=alert(1)> <b>Jaguar</b>',
        },
      ],
    });
    await typeAndSearch(el, 'jaguar');

    const highlight = el.querySelector('.result__highlight')!;
    expect(highlight.querySelector('img')).toBeNull();
    expect(highlight.innerHTML).toContain('&lt;img');
    expect(highlight.querySelector('mark')?.textContent).toContain('Jaguar');
  });

  it('shows an empty state when nothing matches', async () => {
    const el = await setup();
    service.result = makeResult({ total: 0, items: [] });
    await typeAndSearch(el, 'nothing');
    expect(el.textContent).toContain('No objects found');
  });

  it('sends the collection filter with the search', async () => {
    const el = await setup();
    const select = el.querySelector<HTMLSelectElement>('.search-bar__collection')!;
    select.value = 'col-bot';
    select.dispatchEvent(new Event('change'));
    fixture.detectChanges();
    await typeAndSearch(el, 'quercus');

    expect(service.searchCalls.at(-1)?.collectionId).toBe('col-bot');
  });

  it('does not search on an empty query', async () => {
    const el = await setup();
    const button = el.querySelector<HTMLButtonElement>('.search-bar__button')!;
    expect(button.disabled).toBe(true);
    expect(service.searchCalls).toEqual([]);
  });
});
