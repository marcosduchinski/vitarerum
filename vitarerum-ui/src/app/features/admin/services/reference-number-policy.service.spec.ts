import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { API_BASE_URL } from '@core/config/app-config.model';

import { ReferenceNumberPolicyService } from './reference-number-policy.service';

describe('ReferenceNumberPolicyService', () => {
  let service: ReferenceNumberPolicyService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: API_BASE_URL, useValue: 'https://api.example.test/' },
        ReferenceNumberPolicyService,
      ],
    });
    service = TestBed.inject(ReferenceNumberPolicyService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    http.verify();
  });

  it('lists policies with an optional kind filter', () => {
    service.list('PROPOSAL').subscribe();

    const request = http.expectOne(
      'https://api.example.test/admin/reference-number-policies?kind=PROPOSAL',
    );
    expect(request.request.method).toBe('GET');
    request.flush([]);
  });

  it('previews a mask', () => {
    service
      .preview({
        kind: 'COLLECTION_USE_PROJECT',
        mask: 'CUP-XXXXXXXX',
        sampleDate: '2026-07-23',
      })
      .subscribe();

    const request = http.expectOne(
      'https://api.example.test/admin/reference-number-policies/preview',
    );
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual({
      kind: 'COLLECTION_USE_PROJECT',
      mask: 'CUP-XXXXXXXX',
      sampleDate: '2026-07-23',
    });
    request.flush({});
  });

  it('creates a draft policy', () => {
    service.create({ kind: 'PROPOSAL', mask: 'VRP-YYYYMMDD-XXXX' }).subscribe();

    const request = http.expectOne('https://api.example.test/admin/reference-number-policies');
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual({ kind: 'PROPOSAL', mask: 'VRP-YYYYMMDD-XXXX' });
    request.flush({});
  });

  it('activates and deactivates a policy', () => {
    service.activate('policy-1').subscribe();
    const activateRequest = http.expectOne(
      'https://api.example.test/admin/reference-number-policies/policy-1/activate',
    );
    expect(activateRequest.request.method).toBe('POST');
    activateRequest.flush({});

    service.deactivate('policy-1').subscribe();
    const deactivateRequest = http.expectOne(
      'https://api.example.test/admin/reference-number-policies/policy-1/deactivate',
    );
    expect(deactivateRequest.request.method).toBe('POST');
    deactivateRequest.flush({});
  });
});
