import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap } from '@angular/router';
import { computed, signal } from '@angular/core';
import { Observable, of } from 'rxjs';

import { IDENTITY_SERVICE } from '@core/auth/identity.service';
import { IdentitySession } from '@core/auth/models/identity-session.model';

import {
  AgenticTrajectoryEvent,
  CandidateAgentAnalysis,
  FullAgenticInvestigation,
  FullAgenticReadiness,
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

function makeAnalysis(candidateId: string): CandidateAgentAnalysis {
  return {
    id: 'analysis-1',
    candidateId,
    runId: 'run-1',
    status: 'COMPLETED',
    model: 'gemma4:12b',
    promptVersionId: 'prompt-version-1',
    promptVersion: 'grounded-reader-v1',
    inputHash: 'input-hash',
    responseHash: 'response-hash',
    analysis: {
      summary: 'The publication is relevant to the consulted object.',
      supportingEvidence: ['Inventory number found in the indexed text.'],
      contradictions: [],
      missingEvidence: [],
      recommendedAction: 'PRESENT_FOR_REVIEW',
      proposedQueries: [],
      reasoningSummary: 'The grounded passage supports human review.',
      confidence: 'HIGH',
    },
    startedAt: '2026-08-18T10:00:00Z',
    completedAt: '2026-08-18T10:00:01Z',
    latencyMs: 1000,
    errorMessage: null,
    createdBy: 'perm-bob-curatorial',
    staffFeedback: null,
    feedbackComment: null,
    feedbackBy: null,
    feedbackAt: null,
  };
}

class ApiStub {
  watch = makeWatch();
  lookupCalls: readonly (readonly string[])[] = [];
  statusCalls: { watchId: string; status: ScientificReturnWatchStatus }[] = [];
  intervalCalls: { watchId: string; reviewIntervalDays: number }[] = [];
  fullAgentic: FullAgenticInvestigation[] = [];
  trajectory: AgenticTrajectoryEvent[] = [];
  startedFullAgentic: string[] = [];
  readiness: FullAgenticReadiness = {
    enabled: true,
    requestedSources: ['CROSSREF', 'EUROPE_PMC'],
    operationalSources: ['CROSSREF', 'EUROPE_PMC'],
    unavailableSources: [],
    inspectableEvidenceSources: ['EUROPE_PMC'],
    configurationValid: true,
    message: null,
  };

  lookupWatches(projectIds: readonly string[]) {
    this.lookupCalls = [...this.lookupCalls, projectIds];
    return of({
      items: projectIds.map((projectId) => ({
        projectId,
        watch: this.watch,
        eligible: true,
        ineligibilityReason: null,
      })),
    });
  }

  getFullAgenticReadiness(): Observable<FullAgenticReadiness> {
    return of(this.readiness);
  }

  candidates: ScientificReturnCandidate[] = [];
  candidateStatusQueries: (string | null)[] = [];

  listCandidates(
    _projectId: string,
    status: string | null,
  ): Observable<ScientificReturnCandidatesPage> {
    this.candidateStatusQueries.push(status);
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

  candidateInvestigations: ScientificReturnInvestigation[] = [];
  analyses: CandidateAgentAnalysis[] = [];

  listCandidateInvestigations(): Observable<readonly ScientificReturnInvestigation[]> {
    return of(this.candidateInvestigations);
  }

  listAgentAnalyses(): Observable<readonly CandidateAgentAnalysis[]> {
    return of(this.analyses);
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

  /** The candidate id the review queue would have put in the URL, if any. */
  let focusedCandidateId: string | null = null;

  beforeEach(async () => {
    api = new ApiStub();
    focusedCandidateId = null;

    await TestBed.configureTestingModule({
      imports: [ScientificReturnPanelComponent],
      providers: [
        {
          provide: ActivatedRoute,
          useValue: {
            get snapshot() {
              return {
                queryParamMap: convertToParamMap(
                  focusedCandidateId ? { candidate: focusedCandidateId } : {},
                ),
              };
            },
          },
        },
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

  it('says where the evidence of an agent-found candidate is held', async () => {
    // The full-agentic flow writes no CandidateEvidence row: what it verified
    // lives in the reader analysis. An empty list under the heading would read
    // as "no evidence", which is the opposite of the truth.
    api.candidates = [
      { ...makeCandidate('candidate-agent', 'PENDING'), agenticCreated: true },
      makeCandidate('candidate-plain', 'PENDING'),
    ];
    fixture = TestBed.createComponent(ScientificReturnPanelComponent);
    fixture.componentRef.setInput('projectId', 'project-1');
    await settle();

    const root = fixture.nativeElement as HTMLElement;
    const blocks = [...root.querySelectorAll('.evidence-block')];
    expect(blocks[0].querySelector('.evidence-block__empty')?.textContent).toContain(
      'Found by the autonomous agent',
    );
    expect(blocks[0].querySelector('.evidence-block__link')?.textContent?.trim()).toBe(
      'Reader analysis',
    );
    // A candidate the agent never touched is genuinely unevidenced, says so,
    // and offers no reader analysis to open.
    expect(blocks[1].querySelector('.evidence-block__empty')?.textContent).toContain(
      'No evidence recorded',
    );
    expect(blocks[1].querySelector('.evidence-block__link')).toBeNull();

    blocks[0].querySelector<HTMLButtonElement>('.evidence-block__link')!.click();
    await settle();
    expect(root.querySelector('[role="dialog"]')?.textContent).toContain('Reader analysis');
  });

  it('keeps the reader analysis reachable on an enriched candidate that has evidence', async () => {
    api.candidates = [
      {
        ...makeCandidate('candidate-enriched', 'PENDING'),
        agenticRediscovered: true,
        evidences: [
          {
            id: 'ev-1',
            type: 'INVENTORY_NUMBER',
            strength: 'PRIMARY',
            value: 'MB06-005747',
            sourceField: 'title',
            explanation: 'The bibliographic record mentions the consulted inventory number.',
            objectId: null,
          },
        ],
      },
    ];
    fixture = TestBed.createComponent(ScientificReturnPanelComponent);
    fixture.componentRef.setInput('projectId', 'project-1');
    await settle();

    const block = (fixture.nativeElement as HTMLElement).querySelector('.evidence-block')!;
    expect(block.querySelector('.evidence-block__empty')).toBeNull();
    expect(block.querySelector('.evidence-block__link')).not.toBeNull();
  });

  it('shows and marks the candidate the review queue linked to, whatever its status', async () => {
    // The queue links to a decided candidate as readily as a pending one, and
    // the default pending filter would hide the very row the link promised.
    focusedCandidateId = 'candidate-decided';
    api.candidates = [
      makeCandidate('candidate-pending', 'PENDING'),
      makeCandidate('candidate-decided', 'CONFIRMED'),
    ];
    fixture = TestBed.createComponent(ScientificReturnPanelComponent);
    fixture.componentRef.setInput('projectId', 'project-1');
    await settle();

    expect(api.candidateStatusQueries.at(-1)).toBeNull();
    const root = fixture.nativeElement as HTMLElement;
    const focused = root.querySelector('#candidate-candidate-decided');
    expect(focused).not.toBeNull();
    expect(focused!.getAttribute('data-focused')).toBe('true');
    expect(
      root.querySelector('#candidate-candidate-pending')!.getAttribute('data-focused'),
    ).toBeNull();
  });

  it('leaves the queue filter on pending when no candidate was linked', async () => {
    api.candidates = [makeCandidate('candidate-1', 'PENDING')];
    fixture = TestBed.createComponent(ScientificReturnPanelComponent);
    fixture.componentRef.setInput('projectId', 'project-1');
    await settle();

    expect(api.candidateStatusQueries.at(-1)).toBe('PENDING');
    expect((fixture.nativeElement as HTMLElement).querySelector('[data-focused]')).toBeNull();
  });

  it('opens each candidate history in its own dialog', async () => {
    api.candidates = [{ ...makeCandidate('candidate-1', 'PENDING'), agenticCreated: true }];
    api.candidateInvestigations = [makeInvestigation('inv-candidate', 'candidate-1')];
    api.analyses = [makeAnalysis('candidate-1')];
    fixture = TestBed.createComponent(ScientificReturnPanelComponent);
    fixture.componentRef.setInput('projectId', 'project-1');
    await settle();

    const root = () => fixture.nativeElement as HTMLElement;
    const dialogs = () => root().querySelectorAll('[role="dialog"]');
    const clickButton = async (label: string) => {
      [...root().querySelectorAll('button')]
        .find((button) => button.textContent?.includes(label))!
        .click();
      await settle();
    };

    expect(dialogs()).toHaveLength(0);

    await clickButton('Investigation history');
    expect(dialogs()).toHaveLength(1);
    expect(root().textContent).toContain('Investigation history');
    expect(dialogs()[0].textContent?.match(/Assisted investigation/g)).toHaveLength(1);
    expect(dialogs()[0].querySelector('app-agent-execution-card h4')?.textContent).toContain(
      'Enrichment',
    );
    expect(dialogs()[0].querySelectorAll('.execution-card__meta div')).toHaveLength(4);
    // The dialog names the publication it belongs to.
    expect(root().textContent).toContain('Publication candidate-1');

    root().querySelector<HTMLButtonElement>('[aria-label="Close investigation history"]')!.click();
    await settle();
    expect(dialogs()).toHaveLength(0);

    // The reader analysis is a separate dialog, not the same panel reused.
    await clickButton('Reader analysis');
    expect(dialogs()).toHaveLength(1);
    expect(root().textContent).toContain('Reader analysis');
    expect(dialogs()[0].querySelector('app-agent-execution-card h4')?.textContent).toContain(
      'Reader assessment',
    );
    expect(dialogs()[0].querySelectorAll('.execution-card__meta div')).toHaveLength(3);

    root().querySelector<HTMLButtonElement>('[aria-label="Close reader analysis"]')!.click();
    await settle();
    expect(dialogs()).toHaveLength(0);
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

  it('loads an optional watch through lookup without relying on a 404 response', () => {
    expect(api.lookupCalls).toEqual([['project-1']]);
  });

  it('refreshes the candidates produced by autonomous investigations', async () => {
    expect((fixture.nativeElement as HTMLElement).textContent).not.toContain(
      'Publication candidate-refreshed',
    );
    const candidateLoadsBeforeRefresh = api.candidateStatusQueries.length;

    api.candidates = [makeCandidate('candidate-refreshed', 'PENDING')];
    const refresh = [...(fixture.nativeElement as HTMLElement).querySelectorAll('button')].find(
      (button) => button.textContent?.trim() === 'Refresh',
    )!;
    refresh.click();
    await settle();

    expect(api.candidateStatusQueries).toHaveLength(candidateLoadsBeforeRefresh + 1);
    expect((fixture.nativeElement as HTMLElement).textContent).toContain(
      'Publication candidate-refreshed',
    );
  });

  it('explains invalid agentic configuration and refuses to enqueue', async () => {
    api.readiness = {
      ...api.readiness,
      operationalSources: ['CROSSREF'],
      inspectableEvidenceSources: [],
      configurationValid: false,
      message: 'No operational source can return inspectable inventory text',
    };
    fixture.destroy();
    fixture = TestBed.createComponent(ScientificReturnPanelComponent);
    fixture.componentRef.setInput('projectId', 'project-1');
    await settle();

    const button = [...(fixture.nativeElement as HTMLElement).querySelectorAll('button')].find(
      (item) => item.textContent?.includes('Start autonomous search'),
    )!;
    expect(button.disabled).toBe(true);
    expect((fixture.nativeElement as HTMLElement).textContent).toContain(
      'No operational source can return inspectable inventory text',
    );
    button.click();

    expect(api.startedFullAgentic).toEqual([]);
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
      {
        id: 'event-19',
        sequence: 19,
        kind: 'STOPPED',
        occurredAt: '2026-08-30T04:40:00Z',
        payload: { status: 'COMPLETED' },
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

  it('cuts the trajectory at each replanning and names the source behind a reading', async () => {
    api.fullAgentic = [
      {
        id: 'full-agentic-grouped',
        watchId: 'watch-1',
        objective: 'DISCOVER_CANDIDATE',
        candidateId: null,
        searchRunId: null,
        status: 'COMPLETED',
        budget: {},
        usage: { queries: 3, candidates: 0 },
        createdBy: 'perm-bob-curatorial',
        createdAt: '2026-08-30T04:35:00Z',
        startedAt: '2026-08-30T04:35:01Z',
        completedAt: '2026-08-30T04:40:00Z',
        heartbeatAt: null,
        failureReason: null,
      },
    ];
    // The shape the flow actually writes: the memory read before any plan, then
    // a fan-out across sources whose records are pooled before being assessed,
    // then a second plan. Only the planning events carry the iteration.
    api.trajectory = [
      {
        id: 'e1',
        sequence: 1,
        kind: 'MEMORY_RETRIEVED',
        occurredAt: '2026-08-30T04:35:02Z',
        payload: { knowledgeItemIds: ['k1'] },
      },
      {
        id: 'e2',
        sequence: 2,
        kind: 'PLAN_CREATED',
        occurredAt: '2026-08-30T04:35:05Z',
        payload: { iteration: 1, searches: [{}, {}], contractVersion: 'v3' },
      },
      {
        id: 'e3',
        sequence: 3,
        kind: 'TOOL_COMPLETED',
        occurredAt: '2026-08-30T04:35:08Z',
        payload: { source: 'CROSSREF', query: 'MB06-5747', resultCount: 12 },
      },
      {
        id: 'e4',
        sequence: 4,
        kind: 'TOOL_COMPLETED',
        occurredAt: '2026-08-30T04:35:09Z',
        payload: { source: 'OPENALEX', query: 'MB06-5747', resultCount: 5 },
      },
      {
        id: 'e5',
        sequence: 5,
        kind: 'ARTICLE_ASSESSED',
        occurredAt: '2026-08-30T04:35:20Z',
        payload: {
          source: 'OPENALEX',
          query: 'MB06-5747',
          relevant: true,
          confidence: 'HIGH',
          inventoryEvidenceStatus: 'OBSERVED',
        },
      },
      {
        id: 'e6',
        sequence: 6,
        kind: 'PLAN_CREATED',
        occurredAt: '2026-08-30T04:36:00Z',
        payload: { iteration: 2, searches: [{}], contractVersion: 'v3' },
      },
      {
        id: 'e7',
        sequence: 7,
        kind: 'STOPPED',
        occurredAt: '2026-08-30T04:40:00Z',
        payload: { status: 'COMPLETED' },
      },
    ];
    fixture = TestBed.createComponent(ScientificReturnPanelComponent);
    fixture.componentRef.setInput('projectId', 'project-1');
    await settle();

    (fixture.nativeElement as HTMLElement)
      .querySelector<HTMLButtonElement>('[aria-labelledby="agentic-workspace-heading"] .run-row')!
      .click();
    await settle();

    const root = fixture.nativeElement as HTMLElement;
    expect(
      [...root.querySelectorAll('.trajectory-iteration')].map((item) => item.textContent?.trim()),
    ).toEqual(['Iteration 1', 'Iteration 2']);

    // The memory read comes before any plan, so it leads the list under no
    // heading; the searches and the reading inherit the plan they followed.
    const groups = [...root.querySelectorAll('.investigation-detail > *')];
    expect(groups[1].className).toBe('trajectory-event');
    expect(groups[1].textContent).toContain('Curatorial memory read');
    expect(groups[2].className).toBe('trajectory-iteration');
    expect(groups[7].className).toBe('trajectory-iteration');

    // A verdict now says which search produced the article it judged.
    const assessed = [...root.querySelectorAll('.trajectory-event')].find((row) =>
      row.textContent?.includes('Article read'),
    )!;
    expect(assessed.textContent?.replace(/\s+/g, ' ')).toContain(
      'OPENALEX · MB06-5747 · relevant · HIGH · OBSERVED',
    );
  });

  it('marks which trajectory steps crossed the agent boundary', async () => {
    api.fullAgentic = [
      {
        id: 'full-agentic-flow',
        watchId: 'watch-1',
        objective: 'DISCOVER_CANDIDATE',
        candidateId: null,
        searchRunId: null,
        status: 'COMPLETED',
        budget: {},
        usage: { queries: 1, candidates: 1 },
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
        id: 'event-1',
        sequence: 1,
        kind: 'PLAN_CREATED',
        occurredAt: '2026-08-30T04:35:10Z',
        payload: { searches: [{ query: 'MB06-5747' }], contractVersion: 'v3' },
      },
      {
        id: 'event-2',
        sequence: 2,
        kind: 'TOOL_COMPLETED',
        occurredAt: '2026-08-30T04:35:12Z',
        payload: { source: 'CROSSREF', query: 'MB06-5747', resultCount: 3 },
      },
      {
        // Sending the query is the system executing the plan, not the model
        // speaking, so it stays unmarked next to the two that are.
        id: 'event-3',
        sequence: 3,
        kind: 'TOOL_STARTED',
        occurredAt: '2026-08-30T04:35:11Z',
        payload: { source: 'CROSSREF', query: 'MB06-5747' },
      },
      {
        id: 'event-4',
        sequence: 4,
        kind: 'STOPPED',
        occurredAt: '2026-08-30T04:40:00Z',
        payload: { status: 'COMPLETED' },
      },
    ];
    fixture = TestBed.createComponent(ScientificReturnPanelComponent);
    fixture.componentRef.setInput('projectId', 'project-1');
    await settle();

    (fixture.nativeElement as HTMLElement)
      .querySelector<HTMLButtonElement>('[aria-labelledby="agentic-workspace-heading"] .run-row')!
      .click();
    await settle();

    const flows = [
      ...(fixture.nativeElement as HTMLElement).querySelectorAll('.trajectory-event__flow'),
    ];
    expect(flows.map((flow) => flow.getAttribute('data-flow'))).toEqual([
      'out',
      'in',
      'none',
      'none',
    ]);
    // A step on neither side of the model gets no icon, only the column that
    // keeps the rows aligned.
    expect(flows[2].textContent?.trim()).toBe('');
    expect(flows[3].textContent?.trim()).toBe('');
    expect(flows[0].textContent).toContain('Produced by the model');
    expect(flows[1].textContent).toContain('Given to the model');
    // Robot, balloon and sound waves are drawn in place: PrimeIcons has none
    // of the three. The cue and the side the robot stands on carry the
    // direction on their own, before the colour is read.
    expect(flows[0].querySelector('.agent-flow__balloon')).not.toBeNull();
    expect(flows[0].querySelector('.agent-flow__robot')?.getAttribute('transform')).toBe(
      'translate(0, 3)',
    );
    expect(flows[1].querySelector('.agent-flow__waves')).not.toBeNull();
    expect(flows[1].querySelector('.agent-flow__robot')?.getAttribute('transform')).toBe(
      'translate(17, 3)',
    );
    expect(flows[2].querySelector('app-agent-flow-icon')).toBeNull();
  });
});
