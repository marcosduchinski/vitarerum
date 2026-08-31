import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { API_BASE_URL } from '@core/config/app-config.model';

import { ScientificReturnApiService } from './scientific-return-api.service';

describe('ScientificReturnApiService', () => {
  let service: ScientificReturnApiService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: API_BASE_URL, useValue: 'https://api.example.test/api/v1' },
        ScientificReturnApiService,
      ],
    });
    service = TestBed.inject(ScientificReturnApiService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('activates monitoring with the initial review interval', () => {
    service.activateWatch('project-1', 90).subscribe();

    const request = http.expectOne(
      'https://api.example.test/api/v1/scientific-return/projects/project-1/watch',
    );
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual({ reviewIntervalDays: 90 });
    request.flush({});
  });

  it('looks up watches and creates a configured paused watch', () => {
    service.lookupWatches(['project-1', 'project-2']).subscribe();
    const lookup = http.expectOne(
      'https://api.example.test/api/v1/scientific-return/watches/lookup',
    );
    expect(lookup.request.method).toBe('POST');
    expect(lookup.request.body).toEqual({ projectIds: ['project-1', 'project-2'] });
    lookup.flush({ items: [] });

    service
      .createWatch('project-1', {
        reviewIntervalDays: 30,
        scheduleAnchorAt: '2026-09-01T00:00:00.000Z',
        startImmediately: false,
      })
      .subscribe();
    const create = http.expectOne(
      'https://api.example.test/api/v1/scientific-return/projects/project-1/watch',
    );
    expect(create.request.body).toEqual({
      reviewIntervalDays: 30,
      scheduleAnchorAt: '2026-09-01T00:00:00.000Z',
      startImmediately: false,
    });
    create.flush({});
  });

  it('updates watch configuration in a single patch', () => {
    service
      .updateWatch('watch-1', {
        scheduleAnchorAt: '2026-09-01T00:00:00.000Z',
        reviewIntervalDays: 60,
      })
      .subscribe();
    const request = http.expectOne(
      'https://api.example.test/api/v1/scientific-return/watches/watch-1',
    );
    expect(request.request.method).toBe('PATCH');
    expect(request.request.body).toEqual({
      scheduleAnchorAt: '2026-09-01T00:00:00.000Z',
      reviewIntervalDays: 60,
    });
    request.flush({});
  });

  it('runs a watch and lists its auditable trajectories', () => {
    service.runWatch('watch-1').subscribe();
    const run = http.expectOne(
      'https://api.example.test/api/v1/scientific-return/watches/watch-1/runs',
    );
    expect(run.request.method).toBe('POST');
    run.flush({});

    service.listRuns('watch-1').subscribe();
    const history = http.expectOne(
      'https://api.example.test/api/v1/scientific-return/watches/watch-1/runs?page=0&size=10',
    );
    expect(history.request.method).toBe('GET');
    history.flush({ content: [], page: 0, size: 10, totalElements: 0, totalPages: 0 });
  });

  it('sends a human decision separately from candidate discovery', () => {
    service
      .decideCandidate('candidate-1', {
        decision: 'DISMISS',
        justification: 'Homonymous author.',
      })
      .subscribe();

    const request = http.expectOne(
      'https://api.example.test/api/v1/scientific-return/candidates/candidate-1/decision',
    );
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual({
      decision: 'DISMISS',
      justification: 'Homonymous author.',
    });
    request.flush({});
  });

  it('loads the global review queue with operational filters', () => {
    service
      .listReviewQueue({
        status: 'PENDING',
        source: 'CROSSREF',
        evidenceStrength: 'PRIMARY',
        page: 1,
        size: 20,
      })
      .subscribe();

    const request = http.expectOne(
      'https://api.example.test/api/v1/scientific-return/candidates?status=PENDING&source=CROSSREF&evidenceStrength=PRIMARY&page=1&size=20',
    );
    expect(request.request.method).toBe('GET');
    request.flush({ content: [], page: 1, size: 20, totalElements: 0, totalPages: 0 });
  });

  it('keeps full-agentic reader history and staff feedback on separate endpoints', () => {
    service.listAgentAnalyses('candidate-1').subscribe();
    const history = http.expectOne(
      'https://api.example.test/api/v1/scientific-return/candidates/candidate-1/agent-analyses',
    );
    expect(history.request.method).toBe('GET');
    history.flush([]);

    service.recordAgentAnalysisFeedback('analysis-1', 'USEFUL').subscribe();
    const feedback = http.expectOne(
      'https://api.example.test/api/v1/scientific-return/agent-analyses/analysis-1/feedback',
    );
    expect(feedback.request.method).toBe('POST');
    expect(feedback.request.body).toEqual({ feedback: 'USEFUL' });
    feedback.flush({});
  });

  it('starts the full agent with an idempotency key and lists its runs', () => {
    service.startFullAgenticInvestigation('watch-1').subscribe();
    const start = http.expectOne(
      'https://api.example.test/api/v1/scientific-return/watches/watch-1/full-agentic-investigations',
    );
    expect(start.request.method).toBe('POST');
    expect(start.request.headers.get('Idempotency-Key')).toBeTruthy();
    expect(start.request.body).toEqual({ objective: 'DISCOVER_CANDIDATE' });
    start.flush({});

    service.listFullAgenticInvestigations('watch-1').subscribe();
    const history = http.expectOne(
      'https://api.example.test/api/v1/scientific-return/watches/watch-1/full-agentic-investigations',
    );
    expect(history.request.method).toBe('GET');
    history.flush([]);
  });

  it('stores curator examples and proposes learning from a decision', () => {
    service
      .listKnowledgeItems({
        status: 'ACTIVE',
        kind: 'INVENTORY_VARIATION_EXAMPLE',
        inventoryNumber: 'MB06-5747',
        page: 1,
        size: 25,
      })
      .subscribe();
    const list = http.expectOne(
      'https://api.example.test/api/v1/scientific-return/knowledge-items?status=ACTIVE&kind=INVENTORY_VARIATION_EXAMPLE&inventoryNumber=MB06-5747&page=1&size=25',
    );
    expect(list.request.method).toBe('GET');
    list.flush({ content: [], page: 1, size: 25, totalElements: 0, totalPages: 0, counts: {} });

    service
      .createInventoryExample({
        registeredNumber: 'MUHNAC/MB06-005747',
        observedForm: 'MB06-5747',
        content: 'The citation omitted internal zeroes.',
      })
      .subscribe();
    const create = http.expectOne(
      'https://api.example.test/api/v1/scientific-return/knowledge-items',
    );
    expect(create.request.body.kind).toBe('INVENTORY_VARIATION_EXAMPLE');
    create.flush({});

    service
      .replaceKnowledgeItem('knowledge-1', {
        registeredNumber: 'MUHNAC/MB06-005747',
        observedForm: 'MB06 5747',
        content: 'Corrected wording.',
      })
      .subscribe();
    const replace = http.expectOne(
      'https://api.example.test/api/v1/scientific-return/knowledge-items/knowledge-1',
    );
    expect(replace.request.method).toBe('PUT');
    replace.flush({});

    service.getKnowledgeHistory('knowledge-1').subscribe();
    const history = http.expectOne(
      'https://api.example.test/api/v1/scientific-return/knowledge-items/knowledge-1/history',
    );
    expect(history.request.method).toBe('GET');
    history.flush([]);

    service.proposeKnowledge('candidate-1', 'This acronym belongs to archaeology.').subscribe();
    const proposal = http.expectOne(
      'https://api.example.test/api/v1/scientific-return/candidates/candidate-1/knowledge-proposals',
    );
    expect(proposal.request.method).toBe('POST');
    expect(proposal.request.body).toEqual({
      explanation: 'This acronym belongs to archaeology.',
    });
    proposal.flush({});
  });
});
