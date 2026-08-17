import { HttpErrorResponse } from '@angular/common/http';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { Observable, of, throwError } from 'rxjs';

import { IDENTITY_SERVICE } from '@core/auth/identity.service';
import { IdentityServiceMock } from '@core/auth/identity.service.mock';

import {
  ScientificReturnMetrics,
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

const METRICS: ScientificReturnMetrics = {
  activeWatches: 7,
  runs: 18,
  failedRuns: 1,
  pendingCandidates: 4,
  confirmedCandidates: 12,
  dismissedCandidates: 2,
};

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
  snoozedUntil: null,
  confirmedPublicationEntryId: null,
  firstSeenAt: '2026-08-17T08:00:00Z',
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
  metricsCalls = 0;
  queueCalls = 0;
  metricsFail = false;
  queueFail = false;
  empty = false;
  totalPages = 1;

  getMetrics(): Observable<ScientificReturnMetrics> {
    this.metricsCalls += 1;
    if (this.metricsFail) {
      return throwError(
        () =>
          new HttpErrorResponse({
            status: 503,
            error: { detail: { error: 'METRICS_UNAVAILABLE', message: 'Metrics unavailable' } },
          }),
      );
    }
    return of(METRICS);
  }

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
    const content = this.empty ? [] : [CANDIDATE];
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
    expect(text).toContain('2 verified signals');
    expect(text).toContain('1 primary');
    expect(text).toContain('1 supporting');
    expect(compiled.querySelector('.candidate-dossier[data-status="PENDING"]')).not.toBeNull();
    expect(
      compiled.querySelector<HTMLAnchorElement>('a[href="https://doi.org/10.1000/specimen"]'),
    ).not.toBeNull();
  });

  it('renders operational metrics with independent business meaning', async () => {
    const fixture = await render();
    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';

    expect(text).toContain('7');
    expect(text).toContain('Projects under continued monitoring');
    expect(text).toContain('4');
    expect(text).toContain('Candidates requiring a staff decision');
    expect(text).toContain('12');
    expect(text).toContain('Publications attributed to projects');
    expect(text).toContain('Search executions needing attention');
  });

  it('filters the queue by Europe PMC and resets all filters', async () => {
    const fixture = await render();
    const compiled = fixture.nativeElement as HTMLElement;
    const selects = compiled.querySelectorAll<HTMLSelectElement>('.queue-toolbar select');

    selects[2].value = 'EUROPE_PMC';
    selects[2].dispatchEvent(new Event('change'));
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(api.queries.at(-1)?.source).toBe('EUROPE_PMC');
    expect(compiled.textContent).toContain('Source: Europe PMC');

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
    expect(compiled.textContent).toContain('0 active');
  });

  it('refreshes metrics and candidates together', async () => {
    const fixture = await render();
    const compiled = fixture.nativeElement as HTMLElement;

    buttonByText(compiled, 'Refresh').click();
    fixture.detectChanges();
    await fixture.whenStable();

    expect(api.metricsCalls).toBe(2);
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
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('Candidate pages');
  });

  it('keeps candidate review available when metrics fail and retries only metrics', async () => {
    api.metricsFail = true;
    const fixture = await render();
    const compiled = fixture.nativeElement as HTMLElement;

    expect(compiled.textContent).toContain('Monitoring overview is temporarily unavailable');
    expect(compiled.textContent).toContain(CANDIDATE.title);

    api.metricsFail = false;
    buttonByText(compiled, 'Retry metrics').click();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(api.metricsCalls).toBe(2);
    expect(api.queueCalls).toBe(1);
    expect(compiled.textContent).toContain('Projects under continued monitoring');
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
