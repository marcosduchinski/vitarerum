import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { API_BASE_URL } from '@core/config/app-config.model';

import { UpdateProposalRequest } from '../models/proposal-actions.model';
import { ProposalApiService } from './proposal-api.service';

describe('ProposalApiService', () => {
  let service: ProposalApiService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: API_BASE_URL, useValue: 'https://api.example.test' },
        ProposalApiService,
      ],
    });

    service = TestBed.inject(ProposalApiService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    http.verify();
  });

  it('creates a proposal with the documented body', () => {
    const body = {
      title: 'Specimen study',
      intendedUse: { useType: 'IN_SITU_VISIT' as const, description: 'Research' },
      purpose: 'Research',
      beginDate: '2026-06-01',
      endDate: '2026-06-30',
    };

    service.createProposal(body).subscribe();

    const request = http.expectOne('https://api.example.test/proposals');

    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual(body);
    request.flush({
      proposal: {
        id: 'proposal-1',
        status: 'SUBMITTED',
        intendedUse: { useType: 'IN_SITU_VISIT', description: 'Research' },
        requestedBy: {
          permissionId: 'permission-1',
          user: { id: 'user-1', name: 'Ana', email: 'ana@example.test' },
          group: 'EXTERNAL',
        },
        assignedTo: null,
        submittedAt: '2026-01-01T10:00:00',
      },
      collectionUseProject: {
        id: 'project-1',
        referenceNumber: 'CUP-2026-0001',
        title: 'Specimen study',
        purpose: 'Research',
        intendedUse: { useType: 'IN_SITU_VISIT', description: 'Research' },
        status: 'CREATED',
        beginDate: '2026-06-01',
        endDate: '2026-06-30',
      },
      conversationId: 'conversation-1',
    });
  });

  it('creates a proposal with only opening message fields', () => {
    const body = {
      initialMessageRecipient: 'collections@example.test',
      initialMessageSubject: 'Archive access request',
      initialMessageBody: 'I would like to discuss access to archive materials.',
    };

    service.createProposal(body).subscribe();

    const request = http.expectOne('https://api.example.test/proposals');

    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual(body);
    request.flush({
      proposal: {
        id: 'proposal-1',
        referenceNumber: 'VRP-20260618-0001',
        title: 'Archive access request',
        status: 'SUBMITTED',
        type: 'OTHER',
        requestedBy: {
          permissionId: 'permission-1',
          user: { id: 'user-1', name: 'Ana', email: 'ana@example.test' },
          group: 'EXTERNAL',
        },
        assignedTo: null,
        submittedAt: '2026-06-18T10:00:00',
      },
      conversationId: 'conversation-1',
    });
  });

  it('lists proposals with filters', () => {
    service
      .listProposals({
        status: 'PENDING',
        type: 'IN_SITU_VISIT',
        requestedBy: 'permission-external',
        assignedTo: 'permission-1',
        dateFrom: '2026-01-01',
        dateTo: '2026-01-31',
        search: 'CUP',
        page: 1,
        size: 25,
      })
      .subscribe();

    const request = http.expectOne(
      'https://api.example.test/proposals?status=PENDING&type=IN_SITU_VISIT&requested_by=permission-external&assigned_to=permission-1&date_from=2026-01-01&date_to=2026-01-31&search=CUP&page=1&size=25',
    );

    expect(request.request.method).toBe('GET');
    expect(request.request.params.get('status')).toBe('PENDING');
    expect(request.request.params.get('requested_by')).toBe('permission-external');
    expect(request.request.params.get('assigned_to')).toBe('permission-1');
    request.flush({ content: [], page: 1, size: 25, totalElements: 0, totalPages: 0 });
  });

  it('lists proposals using repeated status filters', () => {
    service.listProposals({ status: ['REJECTED', 'CANCELLED'], page: 0, size: 100 }).subscribe();

    const request = http.expectOne(
      'https://api.example.test/proposals?status=REJECTED&status=CANCELLED&page=0&size=100',
    );

    expect(request.request.method).toBe('GET');
    expect(request.request.params.getAll('status')).toEqual(['REJECTED', 'CANCELLED']);
    request.flush({ content: [], page: 0, size: 100, totalElements: 0, totalPages: 0 });
  });

  it('normalizes intendedUse.useType into the flat type field', () => {
    let listType: string | undefined;
    service.listProposals().subscribe((page) => (listType = page.content[0]?.type));
    http
      .expectOne((r) => r.url === 'https://api.example.test/proposals')
      .flush({
        content: [
          {
            id: 'pr1',
            referenceNumber: 'VRP-20260101-0001',
            title: 'Proposal',
            status: 'PENDING',
            intendedUse: { useType: 'IN_SITU_VISIT', description: 'Comparative study' },
          },
        ],
        page: 0,
        size: 20,
        totalElements: 1,
        totalPages: 1,
      });
    expect(listType).toBe('IN_SITU_VISIT');

    let detailType: string | undefined;
    service.getProposal('pr1').subscribe((p) => (detailType = p.type));
    http.expectOne('https://api.example.test/proposals/pr1').flush({
      id: 'pr1',
      referenceNumber: 'VRP-20260101-0001',
      title: 'Proposal',
      status: 'PENDING',
      intendedUse: { useType: 'EXHIBITION', description: 'Show' },
    });
    expect(detailType).toBe('EXHIBITION');
  });

  it('adds selected catalog snapshots to a proposal', () => {
    const body = {
      objects: [
        {
          inventoryNumber: 'MNHN-MAM-00421',
          displayTitle: 'Lynx pardinus study skin',
          objectName: 'Zoological study skin',
          briefDescriptionSnapshot: 'Historic Iberian lynx reference specimen.',
          category: 'mammalogy',
          description: 'Requested for comparative research.',
        },
      ],
    };

    service.addRequestedObjects('proposal-1', body).subscribe();

    const request = http.expectOne(
      'https://api.example.test/proposals/proposal-1/requested-objects',
    );
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual(body);
    request.flush({
      id: 'proposal-1',
      referenceNumber: 'VRP-20260101-0001',
      title: 'Lynx research',
      status: 'PENDING',
      type: 'IN_SITU_VISIT',
      requestedObjects: [],
    });
  });

  it('defaults missing proposal type data to other', () => {
    let listType: string | undefined;
    service.listProposals().subscribe((page) => (listType = page.content[0]?.type));
    http
      .expectOne((r) => r.url === 'https://api.example.test/proposals')
      .flush({
        content: [
          {
            id: 'pr1',
            referenceNumber: 'VRP-20260101-0001',
            title: 'Proposal',
            status: 'SUBMITTED',
          },
        ],
        page: 0,
        size: 20,
        totalElements: 1,
        totalPages: 1,
      });

    expect(listType).toBe('OTHER');
  });

  it('partially updates proposal metadata and preserves explicit null values', () => {
    const body: UpdateProposalRequest = {
      title: null,
      intendedUse: {
        useType: 'EXHIBITION',
        description: 'Public display of selected collection objects.',
      },
      endDate: null,
    };
    let updatedTitle: string | null | undefined;
    let updatedLastEvent: unknown;

    service.updateProposal('proposal-1', body).subscribe((result) => {
      updatedTitle = result.title;
      updatedLastEvent = result.lastEvent;
    });

    const request = http.expectOne('https://api.example.test/proposals/proposal-1');

    expect(request.request.method).toBe('PATCH');
    expect(request.request.body).toEqual(body);
    expect(request.request.body).not.toHaveProperty('beginDate');
    request.flush({
      id: 'proposal-1',
      referenceNumber: 'VRP-20260101-0001',
      title: null,
      status: 'PENDING',
      beginDate: '2026-06-01',
      endDate: null,
      lastEvent: null,
    });

    expect(updatedTitle).toBeNull();
    expect(updatedLastEvent).toBeNull();
  });

  it('uploads proposal documents as multipart form data', () => {
    const file = new File(['document'], 'research_form.docx', {
      type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    });

    service.uploadDocument('proposal-1', file, 'RESEARCH_FORM').subscribe();

    const request = http.expectOne('https://api.example.test/proposals/proposal-1/documents');

    expect(request.request.method).toBe('POST');
    expect(request.request.body instanceof FormData).toBe(true);
    expect((request.request.body as FormData).get('file')).toBe(file);
    expect((request.request.body as FormData).get('documentType')).toBe('RESEARCH_FORM');
    request.flush({
      id: 'document-1',
      type: 'RESEARCH_FORM',
      fileName: 'research_form.docx',
      fileReference: 'files/document-1',
      submittedAt: '2026-01-01T10:00:00',
    });
  });

  it('downloads a document as a blob', () => {
    let received: Blob | undefined;
    service.downloadDocument('proposal-1', 'document-1').subscribe((blob) => (received = blob));

    const request = http.expectOne(
      'https://api.example.test/proposals/proposal-1/documents/document-1',
    );

    expect(request.request.method).toBe('GET');
    expect(request.request.responseType).toBe('blob');

    const blob = new Blob(['file-bytes']);
    request.flush(blob);
    expect(received).toBe(blob);
  });

  it('posts proposal decision actions to documented endpoints', () => {
    const approveBody = {
      title: 'Specimen study',
      purpose: 'Research',
      beginDate: '2026-06-01',
      endDate: '2026-06-30',
      note: 'Approved',
    };
    service.approveProposal('proposal-1', approveBody).subscribe();

    const request = http.expectOne('https://api.example.test/proposals/proposal-1/approve');

    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual(approveBody);
    request.flush({
      proposal: { id: 'proposal-1', status: 'APPROVED', lastEvent: null },
      collectionUseProject: {
        id: 'project-1',
        referenceNumber: 'CUP-2026-0001',
        title: 'Specimen study',
        status: 'CREATED',
      },
    });
  });
});
