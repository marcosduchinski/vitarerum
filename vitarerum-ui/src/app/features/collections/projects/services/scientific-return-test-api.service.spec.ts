import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { API_BASE_URL } from '@core/config/app-config.model';

import { ScientificReturnTestApiService } from './scientific-return-test-api.service';

describe('ScientificReturnTestApiService', () => {
  let service: ScientificReturnTestApiService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: API_BASE_URL, useValue: 'https://api.example.test/api/v1' },
        ScientificReturnTestApiService,
      ],
    });
    service = TestBed.inject(ScientificReturnTestApiService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('creates sources without sending institutional scope from the browser', () => {
    service
      .createSource({
        name: 'Catalogue',
        kind: 'TEXT_DOCUMENT',
        content: 'Inventory M-01',
        locator: null,
        authors: [],
      })
      .subscribe();
    const request = http.expectOne(
      'https://api.example.test/api/v1/scientific-return/test-sources',
    );
    expect(request.request.method).toBe('POST');
    expect(request.request.body.institutionId).toBeUndefined();
    request.flush({});
  });

  it('starts with an idempotency key and downloads the backend CSV', () => {
    service.startBatch('batch-1').subscribe();
    const start = http.expectOne(
      'https://api.example.test/api/v1/scientific-return/test-batches/batch-1/start',
    );
    expect(start.request.headers.get('Idempotency-Key')).toBeTruthy();
    start.flush({});

    service.exportCsv('batch-1').subscribe();
    const download = http.expectOne(
      'https://api.example.test/api/v1/scientific-return/test-batches/batch-1/export.csv',
    );
    expect(download.request.responseType).toBe('blob');
    download.flush(new Blob(['item_id\r\n']));
  });
});
