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
});
