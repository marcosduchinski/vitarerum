import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { API_BASE_URL } from '@core/config/app-config.model';

import { InstitutionManagementService } from './institution-management.service';

describe('InstitutionManagementService', () => {
  let service: InstitutionManagementService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: API_BASE_URL, useValue: 'https://api.example.test/' },
        InstitutionManagementService,
      ],
    });

    service = TestBed.inject(InstitutionManagementService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    http.verify();
  });

  it('lists institutions with pagination params', () => {
    service.listInstitutions({ page: 1, size: 10 }).subscribe();

    const request = http.expectOne('https://api.example.test/institutions?page=1&size=10');

    expect(request.request.method).toBe('GET');
    request.flush({ content: [], page: 1, size: 10, totalElements: 0, totalPages: 0 });
  });

  it('fetches a single institution by id', () => {
    service.getInstitution('inst-1').subscribe();

    const request = http.expectOne('https://api.example.test/institutions/inst-1');

    expect(request.request.method).toBe('GET');
    request.flush({ id: 'inst-1', name: 'MUHNAC', email: '', address: '', phone: '' });
  });

  it('creates an institution', () => {
    const payload = { name: 'MUHNAC', email: 'a@b.pt', address: 'Lisboa', phone: '1' };
    service.createInstitution(payload).subscribe();

    const request = http.expectOne('https://api.example.test/institutions');

    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual(payload);
    request.flush({ id: 'inst-1', ...payload });
  });

  it('updates an institution', () => {
    const payload = { name: 'New', email: '', address: '', phone: '' };
    service.updateInstitution('inst-1', payload).subscribe();

    const request = http.expectOne('https://api.example.test/institutions/inst-1');

    expect(request.request.method).toBe('PUT');
    expect(request.request.body).toEqual(payload);
    request.flush({ id: 'inst-1', ...payload });
  });

  it('deletes an institution', () => {
    service.deleteInstitution('inst-1').subscribe();

    const request = http.expectOne('https://api.example.test/institutions/inst-1');

    expect(request.request.method).toBe('DELETE');
    request.flush(null);
  });
});
