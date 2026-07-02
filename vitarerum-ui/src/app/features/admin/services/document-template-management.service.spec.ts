import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { API_BASE_URL } from '@core/config/app-config.model';

import { DocumentTemplateManagementService } from './document-template-management.service';

describe('DocumentTemplateManagementService', () => {
  let service: DocumentTemplateManagementService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: API_BASE_URL, useValue: 'https://api.example.test/' },
        DocumentTemplateManagementService,
      ],
    });
    service = TestBed.inject(DocumentTemplateManagementService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    http.verify();
  });

  it('lists templates filtered by use type', () => {
    service.list('IN_SITU_VISIT').subscribe();
    const request = http.expectOne(
      'https://api.example.test/document-templates?useType=IN_SITU_VISIT',
    );
    expect(request.request.method).toBe('GET');
    request.flush([]);
  });

  it('lists all templates when no use type is given', () => {
    service.list().subscribe();
    const request = http.expectOne('https://api.example.test/document-templates');
    expect(request.request.method).toBe('GET');
    request.flush([]);
  });

  it('creates a template as multipart form data', () => {
    const file = new File(['x'], 'form.docx');
    service
      .create({
        useType: 'IN_SITU_VISIT',
        title: 'Safety',
        description: 'desc',
        mandatory: true,
        active: true,
        displayOrder: 2,
        file,
      })
      .subscribe();

    const request = http.expectOne('https://api.example.test/document-templates');
    expect(request.request.method).toBe('POST');
    const body = request.request.body as FormData;
    expect(body.get('useType')).toBe('IN_SITU_VISIT');
    expect(body.get('title')).toBe('Safety');
    expect(body.get('mandatory')).toBe('true');
    expect(body.get('displayOrder')).toBe('2');
    expect(body.get('file')).toBeInstanceOf(File);
    request.flush({});
  });

  it('updates metadata via PATCH', () => {
    service
      .updateMetadata('t1', {
        title: 'New',
        description: 'd',
        mandatory: false,
        active: false,
        displayOrder: 5,
      })
      .subscribe();
    const request = http.expectOne('https://api.example.test/document-templates/t1');
    expect(request.request.method).toBe('PATCH');
    expect(request.request.body).toEqual({
      title: 'New',
      description: 'd',
      mandatory: false,
      active: false,
      displayOrder: 5,
    });
    request.flush({});
  });

  it('replaces the file via PUT multipart', () => {
    service.replaceFile('t1', new File(['x'], 'v2.docx')).subscribe();
    const request = http.expectOne('https://api.example.test/document-templates/t1/file');
    expect(request.request.method).toBe('PUT');
    expect((request.request.body as FormData).get('file')).toBeInstanceOf(File);
    request.flush({});
  });

  it('deletes a template', () => {
    service.remove('t1').subscribe();
    const request = http.expectOne('https://api.example.test/document-templates/t1');
    expect(request.request.method).toBe('DELETE');
    request.flush(null);
  });

  it('downloads the file as a blob', () => {
    service.downloadFile('t1').subscribe();
    const request = http.expectOne('https://api.example.test/document-templates/t1/file');
    expect(request.request.method).toBe('GET');
    expect(request.request.responseType).toBe('blob');
    request.flush(new Blob(['x']));
  });
});
