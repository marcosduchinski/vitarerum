import { ComponentFixture, TestBed } from '@angular/core/testing';
import { computed, signal } from '@angular/core';
import { Observable, of } from 'rxjs';

import { IDENTITY_SERVICE } from '@core/auth/identity.service';
import { IdentitySession } from '@core/auth/models/identity-session.model';

import {
  AgenticTrajectoryEvent,
  FullAgenticInvestigation,
  ScientificReturnCandidate,
  ScientificReturnCandidatesPage,
  ScientificReturnCandidateStatus,
  ScientificReturnInvestigation,
  ScientificReturnWatch,
  ScientificReturnWatchStatus,
  UpdateScientificReturnWatchRequest,
} from '../../models/scientific-return.model';
import { ScientificReturnApiService } from '../../services/scientific-return-api.service';
import { ScientificReturnPanelComponent } from './scientific-return-panel.component';

const SESSION: IdentitySession = {
  accessToken: 'token',
  user: { id: 'u-bob', email: 'bob@example.test', displayName: 'Bob Santos' },
  group: 'CURATORIAL',
  availableGroups: ['CURATORIAL'],
  permissions: [{ permissionId: 'perm-bob-curatorial', group: 'CURATORIAL' }],
};

class IdentityStub {
  readonly sessionState = signal<IdentitySession | null>(SESSION);
  readonly session = this.sessionState.asReadonly();
  readonly isAuthenticated = computed(() => this.session() !== null);
  readonly isStaff = computed(() => this.session()?.group !== 'EXTERNAL');

  getAccessToken(): string | null {
    return this.session()?.accessToken ?? null;
  }

  getPermissionId(): string | null {
    return this.session()?.permissions?.[0]?.permissionId ?? null;
  }
}

function makeWatch(status: ScientificReturnWatchStatus = 'ACTIVE'): ScientificReturnWatch {
  return {
    id: 'watch-1',
    projectId: 'project-1',
    status,
    reviewIntervalDays: 90,
    createdBy: 'perm-bob-curatorial',
    createdAt: '2026-08-18T10:00:00Z',
    lastRunAt: null,
    nextRunAt: '2026-11-16T10:00:00Z',
    scheduleAnchorAt: '2026-08-18T10:00:00Z',
    projectSnapshotId: 'snap-1',
  };
}

const EMPTY_PAGE = { content: [], page: 0, size: 20, totalElements: 0, totalPages: 0 };

function makeCandidate(
  id: string,
  status: ScientificReturnCandidateStatus,
): ScientificReturnCandidate {
  return {
    id,
    watchId: 'watch-1',
    source: 'EUROPE_PMC',
    sourceRecordId: `record-${id}`,
    doi: null,
    title: `Publication ${id}`,
    authors: ['Bob Santos'],
    publicationDate: '2026-05-01',
    abstract: null,
    url: null,
    status,
    confirmedPublicationEntryId: null,
    firstSeenAt: '2026-08-18T10:00:00Z',
    evidences: [],
  };
}

function makeInvestigation(id: string, candidateId: string | null): ScientificReturnInvestigation {
  return {
    id,
    watchId: 'watch-1',
    candidateId,
    objective: candidateId ? 'ENRICH_CANDIDATE' : 'DISCOVER_CANDIDATE',
    status: 'STOPPED',
    mode: 'SUPERVISED',
    stopReason: 'NO_RESULTS',
    currentIteration: 1,
    budget: {
      maxIterations: 1,
      maxQueries: 4,
      maxNewCandidates: 5,
      usedIterations: 1,
      usedQueries: 4,
      createdCandidates: 0,
    },
    startedAt: '2026-08-18T10:00:00Z',
    completedAt: '2026-08-18T10:01:32Z',
    createdBy: 'perm-bob-curatorial',
    previousInvestigationId: null,
    iterations: [],
  };
}

class ApiStub {
  watch = makeWatch();
  statusCalls: { watchId: string; status: ScientificReturnWatchStatus }[] = [];
  intervalCalls: { watchId: string; reviewIntervalDays: number }[] = [];
  fullAgentic: FullAgenticInvestigation[] = [];
  trajectory: AgenticTrajectoryEvent[] = [];
  startedFullAgentic: string[] = [];

  getWatch(): Observable<ScientificReturnWatch> {
    return of(this.watch);
  }

  candidates: ScientificReturnCandidate[] = [];

  listCandidates(): Observable<ScientificReturnCandidatesPage> {
    return of({ ...EMPTY_PAGE, content: this.candidates, totalElements: this.candidates.length });
  }

  listRuns(): Observable<typeof EMPTY_PAGE> {
    return of(EMPTY_PAGE);
  }

  listFullAgenticInvestigations(): Observable<readonly FullAgenticInvestigation[]> {
    return of(this.fullAgentic);
  }

  getFullAgenticTrajectory(): Observable<readonly AgenticTrajectoryEvent[]> {
    return of(this.trajectory);
  }

  startFullAgenticInvestigation(watchId: string): Observable<FullAgenticInvestigation> {
    this.startedFullAgentic.push(watchId);
    const item: FullAgenticInvestigation = {
      id: 'full-agentic-1',
      watchId,
      objective: 'DISCOVER_CANDIDATE',
      candidateId: null,
      searchRunId: null,
      status: 'QUEUED',
      budget: {},
      usage: { queries: 0, candidates: 0 },
      createdBy: 'perm-bob-curatorial',
      createdAt: '2026-08-21T10:00:00Z',
      startedAt: null,
      completedAt: null,
      heartbeatAt: null,
      failureReason: null,
    };
    this.fullAgentic = [item];
    return of(item);
  }

  investigations: ScientificReturnInvestigation[] = [];

  listWatchInvestigations(): Observable<readonly ScientificReturnInvestigation[]> {
    return of(this.investigations);
  }

  updateWatch(
    watchId: string,
    request: UpdateScientificReturnWatchRequest,
  ): Observable<ScientificReturnWatch> {
    if (request.reviewIntervalDays !== undefined) {
      this.intervalCalls.push({ watchId, reviewIntervalDays: request.reviewIntervalDays });
    }
    this.watch = {
      ...this.watch,
      ...request,
      nextRunAt: '2026-09-17T10:00:00Z',
    };
    return of(this.watch);
  }

  changeWatchStatus(
    watchId: string,
    status: ScientificReturnWatchStatus,
  ): Observable<ScientificReturnWatch> {
    this.statusCalls.push({ watchId, status });
    this.watch = { ...this.watch, status };
    return of(this.watch);
  }
}

describe('ScientificReturnPanelComponent', () => {
  let fixture: ComponentFixture<ScientificReturnPanelComponent>;
  let api: ApiStub;

  const closeButton = () =>
    (fixture.nativeElement as HTMLElement).querySelector<HTMLButtonElement>(
      'button[aria-label="Close monitoring"]',
    );
  const dialog = () =>
    (fixture.nativeElement as HTMLElement).querySelector<HTMLElement>('[role="dialog"]');

  // Two rounds: the click handler is async, so its continuation only lands
  // after the promise it awaited has been flushed.
  async function settle(): Promise<void> {
    for (let round = 0; round < 2; round += 1) {
      fixture.detectChanges();
      await fixture.whenStable();
    }
    fixture.detectChanges();
  }

  beforeEach(async () => {
    api = new ApiStub();

    await TestBed.configureTestingModule({
      imports: [ScientificReturnPanelComponent],
      providers: [
        { provide: ScientificReturnApiService, useValue: api },
        { provide: IDENTITY_SERVICE, useValue: new IdentityStub() },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(ScientificReturnPanelComponent);
    fixture.componentRef.setInput('projectId', 'project-1');
    await settle();
  });

  const intervalInput = () =>
    (fixture.nativeElement as HTMLElement).querySelector<HTMLInputElement>(
      'input[aria-label="Review interval in days"]',
    );
  const editIntervalButton = () =>
    (fixture.nativeElement as HTMLElement).querySelector<HTMLButtonElement>(
      'button[aria-label="Edit review interval"]',
    );
  const saveIntervalButton = () =>
    (fixture.nativeElement as HTMLElement).querySelector<HTMLButtonElement>(
      'button[aria-label="Save interval"]',
    );

  async function typeInterval(value: string): Promise<void> {
    const input = intervalInput()!;
    input.value = value;
    input.dispatchEvent(new Event('input'));
    await settle();
  }

  const investigationSection = () =>
    (fixture.nativeElement as HTMLElement).querySelector<HTMLElement>('.watch-investigations');

  const investigationRows = () =>
    investigationSection()!.querySelectorAll<HTMLButtonElement>('.run-row');

  it('lists a discovery recorded before this session, collapsed', async () => {
    // The panel was built before the fixture had investigations; rebuild it so
    // the resource loads them the way a page reload would.
    api.investigations = [makeInvestigation('inv-discovery', null)];
    fixture = TestBed.createComponent(ScientificReturnPanelComponent);
    fixture.componentRef.setInput('projectId', 'project-1');
    await settle();

    const section = investigationSection()!;
    expect(section.textContent).toContain('1 recorded');
    expect(investigationRows()).toHaveLength(1);
    // The row summarises; the trajectory itself stays closed until asked for.
    expect(section.textContent).toContain('No results');
    expect(section.querySelectorAll('.trajectory')).toHaveLength(0);
  });

  it('expands one trajectory at a time', async () => {
    api.investigations = [makeInvestigation('inv-a', null), makeInvestigation('inv-b', null)];
    fixture = TestBed.createComponent(ScientificReturnPanelComponent);
    fixture.componentRef.setInput('projectId', 'project-1');
    await settle();

    investigationRows()[0].click();
    await settle();
    expect(investigationSection()!.querySelectorAll('.trajectory')).toHaveLength(1);
    expect(investigationRows()[0].getAttribute('aria-expanded')).toBe('true');

    investigationRows()[1].click();
    await settle();
    expect(investigationSection()!.querySelectorAll('.trajectory')).toHaveLength(1);
    expect(investigationRows()[0].getAttribute('aria-expanded')).toBe('false');

    investigationRows()[1].click();
    await settle();
    expect(investigationSection()!.querySelectorAll('.trajectory')).toHaveLength(0);
  });

  it('leaves enrichment investigations to their candidate', async () => {
    api.investigations = [makeInvestigation('inv-enrichment', 'candidate-1')];
    fixture = TestBed.createComponent(ScientificReturnPanelComponent);
    fixture.componentRef.setInput('projectId', 'project-1');
    await settle();

    const section = investigationSection()!;
    expect(section.textContent).toContain('0 recorded');
    expect(section.querySelectorAll('.run-row')).toHaveLength(0);
  });

  it('offers enrichment only while the candidate is undecided', async () => {
    api.candidates = [makeCandidate('candidate-pending', 'PENDING')];
    fixture = TestBed.createComponent(ScientificReturnPanelComponent);
    fixture.componentRef.setInput('projectId', 'project-1');
    await settle();

    const enrichmentButtons = () =>
      [...(fixture.nativeElement as HTMLElement).querySelectorAll('button')].filter((button) =>
        button.textContent?.includes('Investigate missing evidence'),
      );
    expect(enrichmentButtons()).toHaveLength(1);

    api.candidates = [
      makeCandidate('candidate-confirmed', 'CONFIRMED'),
      makeCandidate('candidate-dismissed', 'DISMISSED'),
    ];
    fixture = TestBed.createComponent(ScientificReturnPanelComponent);
    fixture.componentRef.setInput('projectId', 'project-1');
    await settle();

    expect(enrichmentButtons()).toHaveLength(0);
    // The audit trail stays reachable for a decided candidate.
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('Investigation history');
  });

  it('queues the autonomous flow explicitly', async () => {
    const button = [...(fixture.nativeElement as HTMLElement).querySelectorAll('button')].find(
      (item) => item.textContent?.includes('Start autonomous search'),
    )!;
    button.click();
    await settle();

    expect(api.startedFullAgentic).toEqual(['watch-1']);
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('queued');
  });

  it('warns that a degraded investigation did not run its full plan', async () => {
    // The resource loads on creation, so the stub is primed before the panel
    // is built rather than reloaded afterwards.
    api.fullAgentic = [
      {
        id: 'full-agentic-degraded',
        watchId: 'watch-1',
        objective: 'DISCOVER_CANDIDATE',
        candidateId: null,
        searchRunId: null,
        status: 'COMPLETED',
        budget: {},
        usage: { queries: 2, candidates: 0 },
        createdBy: 'perm-bob-curatorial',
        createdAt: '2026-08-25T10:00:00Z',
        startedAt: '2026-08-25T10:00:01Z',
        completedAt: '2026-08-25T10:05:00Z',
        heartbeatAt: null,
        failureReason: null,
        degradedReason: 'The planner contract stayed invalid after a retry',
      },
    ];
    fixture = TestBed.createComponent(ScientificReturnPanelComponent);
    fixture.componentRef.setInput('projectId', 'project-1');
    await settle();

    const text = ((fixture.nativeElement as HTMLElement).textContent ?? '')
      .replace(/\s+/g, ' ')
      .trim();
    // COMPLETED with zero candidates must not read as "there is nothing".
    expect(text).toContain('Finished without its full plan');
    expect(text).toContain('no results here does not mean there are none');
    expect(text).toContain('The planner contract stayed invalid after a retry');
  });

  it('saves a new interval and shows the next review the server returned', async () => {
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('90 days');

    editIntervalButton()!.click();
    await settle();
    await typeInterval('30');
    saveIntervalButton()!.click();
    await settle();

    expect(api.intervalCalls).toEqual([{ watchId: 'watch-1', reviewIntervalDays: 30 }]);
    expect(intervalInput()).toBeNull();
    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(text).toContain('30 days');
    expect(text).toContain('Sep 17, 2026');
  });

  it('refuses an interval outside the range the server accepts', async () => {
    editIntervalButton()!.click();
    await settle();

    await typeInterval('400');
    expect(saveIntervalButton()!.disabled).toBe(true);

    await typeInterval('0');
    expect(saveIntervalButton()!.disabled).toBe(true);

    await typeInterval('365');
    expect(saveIntervalButton()!.disabled).toBe(false);
    expect(api.intervalCalls).toHaveLength(0);
  });

  it('does not call the server when the interval is unchanged', async () => {
    editIntervalButton()!.click();
    await settle();
    saveIntervalButton()!.click();
    await settle();

    expect(api.intervalCalls).toHaveLength(0);
    expect(intervalInput()).toBeNull();
  });

  it('asks for confirmation instead of closing on the first click', async () => {
    closeButton()!.click();
    await settle();

    expect(api.statusCalls).toHaveLength(0);
    expect(dialog()?.textContent).toContain('Close monitoring?');
    expect(dialog()?.textContent).toContain('permanent');
  });

  it('leaves the watch untouched when the confirmation is cancelled', async () => {
    closeButton()!.click();
    await settle();

    const cancel = [...dialog()!.querySelectorAll('button')].find(
      (button) => button.textContent?.trim() === 'Keep monitoring',
    )!;
    cancel.click();
    await settle();

    expect(api.statusCalls).toHaveLength(0);
    expect(dialog()).toBeNull();
    expect(closeButton()).not.toBeNull();
  });

  it('closes the watch only after the confirmation is accepted', async () => {
    closeButton()!.click();
    await settle();

    const confirm = [...dialog()!.querySelectorAll('button')].find(
      (button) => button.textContent?.trim() === 'Close monitoring',
    )!;
    confirm.click();
    await settle();

    expect(api.statusCalls).toEqual([{ watchId: 'watch-1', status: 'CLOSED' }]);
    expect(dialog()).toBeNull();
  });

  it('shows what each trajectory event actually says', async () => {
    // The row used to print a number, a kind and a date while the payload beside
    // it carried the searches, the verdicts and the reasons.
    api.fullAgentic = [
      {
        id: 'full-agentic-trajectory',
        watchId: 'watch-1',
        objective: 'DISCOVER_CANDIDATE',
        candidateId: null,
        searchRunId: null,
        status: 'COMPLETED',
        budget: {},
        usage: { queries: 4, candidates: 1 },
        createdBy: 'perm-bob-curatorial',
        createdAt: '2026-08-30T04:35:00Z',
        startedAt: '2026-08-30T04:35:01Z',
        completedAt: '2026-08-30T04:40:00Z',
        heartbeatAt: null,
        failureReason: null,
      },
    ];
    api.trajectory = [
      {
        id: 'event-16',
        sequence: 16,
        kind: 'LLM_CALL_STARTED',
        occurredAt: '2026-08-30T04:35:34Z',
        payload: { phase: 'PLAN', iteration: 2, llmCalls: 3, maxLlmCalls: 20 },
      },
      {
        id: 'event-17',
        sequence: 17,
        kind: 'LLM_CALL_COMPLETED',
        occurredAt: '2026-08-30T04:35:47Z',
        payload: { phase: 'PLAN', durationMs: 12613 },
      },
      {
        id: 'event-18',
        sequence: 18,
        kind: 'ARTICLE_ASSESSED',
        occurredAt: '2026-08-30T04:35:55Z',
        payload: {
          relevant: true,
          confidence: 'MEDIUM',
          inventoryEvidenceStatus: 'NOT_OBSERVED',
          explanation: 'The author surname matches the researcher.',
        },
      },
    ];
    fixture = TestBed.createComponent(ScientificReturnPanelComponent);
    fixture.componentRef.setInput('projectId', 'project-1');
    await settle();

    // The agentic list is its own section; the helper above targets the
    // supervised one.
    const agenticRows = (fixture.nativeElement as HTMLElement).querySelectorAll<HTMLButtonElement>(
      '[aria-labelledby="agentic-workspace-heading"] .run-row',
    );
    agenticRows[0].click();
    await settle();

    const flat = () =>
      ((fixture.nativeElement as HTMLElement).textContent ?? '').replace(/\s+/g, ' ').trim();
    expect(flat()).toContain('Model call charged');
    expect(flat()).toContain('PLAN · 3 of 20');
    expect(flat()).toContain('12.6s');
    expect(flat()).toContain('relevant · MEDIUM · NOT_OBSERVED');
    // The explanation stays behind the row until it is opened.
    expect(flat()).not.toContain('The author surname matches the researcher.');

    const rows = (fixture.nativeElement as HTMLElement).querySelectorAll<HTMLButtonElement>(
      '.trajectory-event__row',
    );
    rows[2].click();
    await settle();
    expect(flat()).toContain('The author surname matches the researcher.');
  });
});
