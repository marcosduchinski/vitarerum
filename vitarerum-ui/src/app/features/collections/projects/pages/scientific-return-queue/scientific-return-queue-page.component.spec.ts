import { HttpErrorResponse } from '@angular/common/http';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { Observable, of, throwError } from 'rxjs';

import { IDENTITY_SERVICE } from '@core/auth/identity.service';
import { IdentityServiceMock } from '@core/auth/identity.service.mock';

import {
  ScientificReturnReviewItem,
  ScientificReturnReviewQueuePage,
} from '../../models/scientific-return.model';
import { ScientificReturnApiService } from '../../services/scientific-return-api.service';
import { ScientificReturnQueuePageComponent } from './scientific-return-queue-page.component';

interface QueueQuery {
  readonly status: string | null;
  readonly source: string | null;
  readonly evidenceStrength: string | null;
  readonly page: number;
  readonly size: number;
}

const CANDIDATE: ScientificReturnReviewItem = {
  id: 'candidate-1',
  projectId: 'project-1',
  watchId: 'watch-1',
  source: 'EUROPE_PMC',
  sourceRecordId: 'PMC1234',
  doi: '10.1000/specimen',
  title: 'A specimen-based revision of Pachydactylus namibensis',
  authors: ['Diogo Parrinha', 'Mariana Marques'],
  publicationDate: '2026',
  abstract: 'The study documents material examined from the museum collection.',
  url: 'https://europepmc.org/article/PMC/1234',
  status: 'PENDING',
  confirmedPublicationEntryId: null,
  firstSeenAt: '2026-08-17T08:00:00Z',
  discoveryBasis: 'AUTHOR_OBJECT',
  searchIntent: 'DISCOVERY',
  searchStrategy: 'AUTHOR_OBJECT',
  inventoryEvidenceStatus: 'VERIFIED',
  groundedInventoryForms: [
    {
      observedForm: 'MUHNAC/MB03-001801',
      sourceField: 'ABSTRACT',
      sourceLocator: null,
    },
  ],
  groundedPassages: ['The examined material includes specimen MUHNAC/MB03-001801 from Lisbon.'],
  rejectedPassageCount: 0,
  rejectedInventoryFormCount: 0,
  evidences: [
    {
      id: 'evidence-1',
      type: 'INVENTORY_NUMBER',
      strength: 'PRIMARY',
      value: 'MUHNAC/MB03-001801',
      sourceField: 'title_or_abstract',
      explanation: 'The bibliographic record mentions the consulted inventory number.',
      objectId: 'object-1',
    },
    {
      id: 'evidence-2',
      type: 'AUTHOR',
      strength: 'SUPPORTING',
      value: 'Diogo Parrinha',
      sourceField: 'authors',
      explanation: 'The author list matches the project researcher.',
      objectId: null,
    },
  ],
};

class ScientificReturnApiServiceStub {
  readonly queries: QueueQuery[] = [];
  queueCalls = 0;
  queueFail = false;
  empty = false;
  totalPages = 1;
  candidates: readonly ScientificReturnReviewItem[] = [CANDIDATE];

  listReviewQueue(query: QueueQuery): Observable<ScientificReturnReviewQueuePage> {
    this.queueCalls += 1;
    this.queries.push(query);
    if (this.queueFail) {
      return throwError(
        () =>
          new HttpErrorResponse({
            status: 503,
            error: { detail: { error: 'QUEUE_UNAVAILABLE', message: 'Queue unavailable' } },
          }),
      );
    }
    const content = this.empty ? [] : this.candidates;
    return of({
      content,
      page: query.page,
      size: query.size,
      totalElements: this.empty ? 0 : this.totalPages * query.size,
      totalPages: this.totalPages,
    });
  }
}

describe('ScientificReturnQueuePageComponent', () => {
  let api: ScientificReturnApiServiceStub;

  beforeEach(async () => {
    api = new ScientificReturnApiServiceStub();

    await TestBed.configureTestingModule({
      imports: [ScientificReturnQueuePageComponent],
      providers: [
        { provide: IDENTITY_SERVICE, useClass: IdentityServiceMock },
        { provide: ScientificReturnApiService, useValue: api },
        provideRouter([]),
      ],
    }).compileComponents();
  });

  async function render(): Promise<ComponentFixture<ScientificReturnQueuePageComponent>> {
    const fixture = TestBed.createComponent(ScientificReturnQueuePageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    return fixture;
  }

  it('loads pending candidates and renders an auditable scientific dossier', async () => {
    const fixture = await render();
    const compiled = fixture.nativeElement as HTMLElement;
    const text = compiled.textContent ?? '';

    expect(api.queries.at(-1)).toEqual({
      status: 'PENDING',
      source: null,
      evidenceStrength: null,
      page: 0,
      size: 20,
    });
    expect(text).toContain('Scientific return review');
    expect(text).toContain('Human decision required');
    expect(text).toContain('A specimen-based revision of Pachydactylus namibensis');
    expect(text).toContain('MUHNAC/MB03-001801');
    expect(text).toContain('Found in Title or abstract');
    expect(text).toContain('Linked to consulted object');
    expect(text).toContain('Inventory number observed in publication');
    expect(text).toContain('Discovery strategy: Author object');
    expect(text).toContain('Observed in Abstract');
    expect(text).toContain('2 structured matches');
    expect(text).toContain('1 grounded passage');
    expect(text).toContain(
      'The examined material includes specimen MUHNAC/MB03-001801 from Lisbon.',
    );
    expect(text).toContain('1 primary');
    expect(text).toContain('1 supporting');
    expect(compiled.querySelector('.candidate-dossier[data-status="PENDING"]')).not.toBeNull();
    expect(
      compiled.querySelector<HTMLAnchorElement>('a[href="https://doi.org/10.1000/specimen"]'),
    ).not.toBeNull();
  });

  it('distinguishes unobserved and unavailable evidence without hiding review', async () => {
    api.candidates = [
      {
        ...CANDIDATE,
        id: 'candidate-not-observed',
        title: 'Discovered by researcher and taxon',
        inventoryEvidenceStatus: 'NOT_OBSERVED',
        groundedInventoryForms: [],
        groundedPassages: [],
        rejectedPassageCount: 1,
        rejectedInventoryFormCount: 2,
        evidences: [],
      },
      {
        ...CANDIDATE,
        id: 'candidate-unavailable',
        title: 'Metadata-only source record',
        inventoryEvidenceStatus: 'UNAVAILABLE',
        groundedInventoryForms: [],
        groundedPassages: [],
        rejectedPassageCount: 0,
        rejectedInventoryFormCount: 0,
        evidences: [],
      },
    ];

    const fixture = await render();
    const compiled = fixture.nativeElement as HTMLElement;
    const text = compiled.textContent ?? '';

    expect(text).toContain('Publication text inspected; inventory number not found');
    expect(text).toContain('Source did not provide inspectable inventory text');
    expect(text).not.toContain('MUHNAC/MB03-001801');
    expect(text).toContain('No verifiable evidence was extracted');
    expect(text).toContain('1 passage claim and 2 inventory claims were rejected');
    expect(compiled.querySelectorAll('a.review-action')).toHaveLength(2);
    expect(compiled.querySelectorAll('[data-evidence-status="VERIFIED"]')).toHaveLength(0);
  });

  it('shows agent-grounded passages independently from structured matches', async () => {
    api.candidates = [
      {
        ...CANDIDATE,
        id: 'candidate-agentic-only',
        evidences: [],
        groundedPassages: ['Material examined includes specimen MB04-001066.'],
      },
    ];

    const fixture = await render();
    const compiled = fixture.nativeElement as HTMLElement;
    const text = compiled.textContent ?? '';

    expect(text).toContain('0 structured matches');
    expect(text).toContain('1 grounded passage');
    expect(text).toContain('Material examined includes specimen MB04-001066.');
    expect(text).not.toContain('0 verified signals');
    expect(
      compiled.querySelector('[aria-label="Agent-grounded publication passages"]'),
    ).not.toBeNull();
  });

  it('filters the queue by Europe PMC and resets all filters', async () => {
    const fixture = await render();
    const compiled = fixture.nativeElement as HTMLElement;
    const selects = compiled.querySelectorAll<HTMLSelectElement>('.filters-bar select');

    selects[2].value = 'EUROPE_PMC';
    selects[2].dispatchEvent(new Event('change'));
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(api.queries.at(-1)?.source).toBe('EUROPE_PMC');
    expect(compiled.querySelector('.filters-bar__clear')).not.toBeNull();

    buttonByText(compiled, 'Clear filters').click();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(api.queries.at(-1)).toEqual({
      status: null,
      source: null,
      evidenceStrength: null,
      page: 0,
      size: 20,
    });
    // With no filter left, the toolbar drops the reset action entirely.
    expect(compiled.querySelector('.filters-bar__clear')).toBeNull();
  });

  it('refreshes the candidate queue', async () => {
    const fixture = await render();
    const compiled = fixture.nativeElement as HTMLElement;

    buttonByText(compiled, 'Refresh').click();
    fixture.detectChanges();
    await fixture.whenStable();

    expect(api.queueCalls).toBe(2);
  });

  it('moves to the next candidate page', async () => {
    api.totalPages = 2;
    const fixture = await render();

    buttonByText(fixture.nativeElement, 'Next').click();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(api.queries.at(-1)?.page).toBe(1);
    // The shared pagination names the range, not just the page number.
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('21–40 of 40 candidates');
  });

  it('renders the queue failure state', async () => {
    api.queueFail = true;
    const fixture = await render();

    expect(
      (fixture.nativeElement as HTMLElement).querySelector('app-error-message'),
    ).not.toBeNull();
  });

  it('renders the empty queue state', async () => {
    api.empty = true;
    const fixture = await render();

    expect((fixture.nativeElement as HTMLElement).textContent).toContain(
      'No candidates in this view',
    );
  });
});

function buttonByText(root: HTMLElement, label: string): HTMLButtonElement {
  const button = Array.from(root.querySelectorAll<HTMLButtonElement>('button')).find((item) =>
    item.textContent?.includes(label),
  );
  if (!button) throw new Error(`Button not found: ${label}`);
  return button;
}
