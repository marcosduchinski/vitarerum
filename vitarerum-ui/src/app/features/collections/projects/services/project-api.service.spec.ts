import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { API_BASE_URL } from '@core/config/app-config.model';

import { ProjectApiService } from './project-api.service';

describe('ProjectApiService', () => {
  let service: ProjectApiService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: API_BASE_URL, useValue: 'https://api.example.test' },
        ProjectApiService,
      ],
    });

    service = TestBed.inject(ProjectApiService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    http.verify();
  });

  it('lists projects with implemented server filters only', () => {
    service
      .listProjects({
        status: 'IN_PROGRESS',
        type: 'IN_SITU_VISIT',
        requestedBy: 'user-1',
        originProjectId: 'project-origin',
        assignedTo: 'permission-1',
        dateFrom: '2026-06-01',
        dateTo: '2026-06-30',
        search: 'specimen',
        page: 3,
        size: 15,
      })
      .subscribe();

    const request = http.expectOne(
      'https://api.example.test/collection-use-projects?status=IN_PROGRESS&type=IN_SITU_VISIT&requestedBy=user-1&originProjectId=project-origin&dateFrom=2026-06-01&dateTo=2026-06-30&search=specimen&page=3&size=15',
    );

    expect(request.request.method).toBe('GET');
    // `requestedBy` is an honored server-side filter; `assignedTo` is not
    // implemented and is stripped before the request.
    expect(request.request.params.get('requestedBy')).toBe('user-1');
    expect(request.request.params.get('originProjectId')).toBe('project-origin');
    expect(request.request.params.has('assignedTo')).toBe(false);
    request.flush({ content: [], page: 3, size: 15, totalElements: 0, totalPages: 0 });
  });

  it('normalizes intendedUse.useType into the flat type field (list + detail)', () => {
    let listType: string | undefined;
    service.listProjects().subscribe((page) => (listType = page.content[0]?.type));
    http
      .expectOne((r) => r.url === 'https://api.example.test/collection-use-projects')
      .flush({
        content: [
          {
            id: 'p1',
            referenceNumber: 'CUP-1',
            title: 'Project',
            purpose: '',
            status: 'IN_PROGRESS',
            beginDate: '2026-06-01',
            endDate: '2026-06-30',
            intendedUse: 'IN_SITU_VISIT',
            proposal: { id: 'pr1', status: 'APPROVED' },
          },
        ],
        page: 0,
        size: 20,
        totalElements: 1,
        totalPages: 1,
      });
    expect(listType).toBe('IN_SITU_VISIT');

    let detailType: string | undefined;
    service.getProject('p1').subscribe((p) => (detailType = p.type));
    http.expectOne('https://api.example.test/collection-use-projects/p1').flush({
      id: 'p1',
      referenceNumber: 'CUP-1',
      title: 'Project',
      purpose: '',
      status: 'IN_PROGRESS',
      beginDate: '2026-06-01',
      endDate: '2026-06-30',
      intendedUse: 'EXHIBITION',
      proposal: { id: 'pr1', status: 'APPROVED' },
    });
    expect(detailType).toBe('EXHIBITION');
  });

  it('creates object log entries and completes projects', () => {
    service
      .createObjectLogEntry('project-1', {
        collectionUseObjectId: 'cuo-1',
        numberOfObjects: 2,
        observations: 'Handled during reading room access.',
      })
      .subscribe();

    const entryRequest = http.expectOne(
      'https://api.example.test/collection-use-projects/project-1/log-entries',
    );

    expect(entryRequest.request.method).toBe('POST');
    expect(entryRequest.request.body).toEqual({
      collectionUseObjectId: 'cuo-1',
      numberOfObjects: 2,
      observations: 'Handled during reading room access.',
    });
    entryRequest.flush({
      id: 'entry-1',
      collectionUseObjectId: 'cuo-1',
      objectReference: {
        inventoryNumber: 'INV-001',
        displayTitle: null,
        objectName: null,
        briefDescriptionSnapshot: null,
      },
      numberOfObjects: 2,
      addedAt: '2026-06-01T10:00:00',
      addedBy: {
        permissionId: 'permission-1',
        user: { id: 'user-1', name: 'Ana', email: 'ana@example.test' },
        group: 'COLLECTIONS_MANAGEMENT',
      },
      observations: 'Handled during reading room access.',
      attachments: [],
    });

    service.completeProject('project-1', { note: 'Completed' }).subscribe();

    const completeRequest = http.expectOne(
      'https://api.example.test/collection-use-projects/project-1/complete',
    );

    expect(completeRequest.request.method).toBe('POST');
    expect(completeRequest.request.body).toEqual({ note: 'Completed' });
    completeRequest.flush({
      id: 'project-1',
      referenceNumber: 'CUP-2026-0001',
      status: 'COMPLETED',
      lastEvent: {
        occurredAt: '2026-07-15T10:00:00',
        type: 'COMPLETED',
        triggeredBy: {
          permissionId: 'permission-1',
          user: { id: 'user-1', name: 'Ana', email: 'ana@example.test' },
          group: 'COLLECTIONS_MANAGEMENT',
        },
        note: 'Completed',
      },
    });
  });

  it('removes project objects with cascade confirmation', () => {
    service
      .removeProjectObjectCascade('project-1', 'object-1', {
        confirmCascade: true,
        reason: 'Wrong object.',
      })
      .subscribe();

    const request = http.expectOne(
      'https://api.example.test/collection-use-projects/project-1/objects/object-1/remove',
    );

    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual({
      confirmCascade: true,
      reason: 'Wrong object.',
    });
    request.flush(null);
  });

  it('creates follow-up projects', () => {
    service
      .createFollowUpProject('project-1', {
        beginDate: '2026-08-10',
        endDate: '2026-08-20',
        objectIds: ['object-1'],
        title: 'Follow-up title',
        purpose: 'Continue research',
        note: 'Continuation after publication.',
      })
      .subscribe();

    const request = http.expectOne(
      'https://api.example.test/collection-use-projects/project-1/follow-ups',
    );

    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual({
      beginDate: '2026-08-10',
      endDate: '2026-08-20',
      objectIds: ['object-1'],
      title: 'Follow-up title',
      purpose: 'Continue research',
      note: 'Continuation after publication.',
    });
    request.flush({
      id: 'project-follow-up',
      referenceNumber: 'CUP-2026-0002',
      title: 'Follow-up title',
      purpose: 'Continue research',
      status: 'CREATED',
      beginDate: '2026-08-10',
      endDate: '2026-08-20',
      intendedUse: 'IN_SITU_VISIT',
      originProjectId: 'project-1',
      proposal: null,
    });
  });

  it('lists object log entries with filters and access log metadata', () => {
    service
      .listObjectLogEntries('project-1', { addedBy: 'permission-1', page: 1, size: 10 })
      .subscribe();

    const request = http.expectOne(
      'https://api.example.test/collection-use-projects/project-1/log-entries?addedBy=permission-1&page=1&size=10',
    );

    expect(request.request.method).toBe('GET');
    expect(request.request.params.get('addedBy')).toBe('permission-1');
    request.flush({
      projectId: 'project-1',
      accessLog: {
        id: 'access-log-1',
        referenceNumber: 'OAL-1A2B3C4D',
        projectId: 'project-1',
        curator: null,
      },
      content: [],
      page: 1,
      size: 10,
      totalElements: 0,
      totalPages: 0,
    });
  });

  it('updates object log entries with the editable fields', () => {
    service
      .updateObjectLogEntry('project-1', 'entry-1', {
        addedAt: '2026-06-02T14:30:00Z',
        numberOfObjects: 3,
        observations: null,
      })
      .subscribe();

    const request = http.expectOne(
      'https://api.example.test/collection-use-projects/project-1/log-entries/entry-1',
    );

    expect(request.request.method).toBe('PATCH');
    expect(request.request.body).toEqual({
      addedAt: '2026-06-02T14:30:00Z',
      numberOfObjects: 3,
      observations: null,
    });
    request.flush({
      id: 'entry-1',
      collectionUseObjectId: 'cuo-1',
      objectReference: {
        inventoryNumber: 'INV-001',
        displayTitle: null,
        objectName: null,
        briefDescriptionSnapshot: null,
      },
      numberOfObjects: 3,
      addedAt: '2026-06-02T14:30:00Z',
      addedBy: {
        permissionId: 'permission-1',
        user: { id: 'user-1', name: 'Ana', email: 'ana@example.test' },
        group: 'COLLECTIONS_MANAGEMENT',
      },
      observations: null,
      attachments: [],
    });
  });

  it('gets object access logs', () => {
    service.getObjectAccessLog('project-1').subscribe();

    const getRequest = http.expectOne(
      'https://api.example.test/collection-use-projects/project-1/object-access-log',
    );

    expect(getRequest.request.method).toBe('GET');
    getRequest.flush({
      id: 'access-log-1',
      referenceNumber: 'OAL-1A2B3C4D',
      projectId: 'project-1',
      curator: null,
    });
  });

  it('uploads log entry attachments as multipart form data', () => {
    const file = new File(['image'], 'photo.jpg', { type: 'image/jpeg' });

    service
      .uploadLogEntryAttachment('project-1', 'entry-1', file, 'IMAGE', 'Front view')
      .subscribe();

    const request = http.expectOne(
      'https://api.example.test/collection-use-projects/project-1/log-entries/entry-1/attachments',
    );

    expect(request.request.method).toBe('POST');
    expect(request.request.body instanceof FormData).toBe(true);
    expect((request.request.body as FormData).get('file')).toBe(file);
    expect((request.request.body as FormData).get('mediaType')).toBe('IMAGE');
    expect((request.request.body as FormData).get('attachmentDescription')).toBe('Front view');
    request.flush({
      fileReference: 'files/photo',
      fileName: 'photo.jpg',
      mediaType: 'IMAGE',
      uploadedAt: '2026-06-01T10:00:00',
      attachmentDescription: 'Front view',
    });
  });

  it('downloads a log entry attachment as a blob with an encoded file reference', () => {
    let received: Blob | undefined;

    // The backend's {file_reference} is a flat segment; encoding protects special
    // characters (e.g. spaces) within it.
    service
      .downloadLogEntryAttachment('project-1', 'entry-1', 'att 12.jpg')
      .subscribe((blob) => (received = blob));

    const request = http.expectOne(
      'https://api.example.test/collection-use-projects/project-1/log-entries/entry-1/attachments/att%2012.jpg',
    );

    expect(request.request.method).toBe('GET');
    expect(request.request.responseType).toBe('blob');

    const blob = new Blob(['file-bytes']);
    request.flush(blob);
    expect(received).toBe(blob);
  });

  it('deletes a log entry attachment with an encoded file reference', () => {
    service.deleteLogEntryAttachment('project-1', 'entry-1', 'att 12.jpg').subscribe();

    const request = http.expectOne(
      'https://api.example.test/collection-use-projects/project-1/log-entries/entry-1/attachments/att%2012.jpg',
    );

    expect(request.request.method).toBe('DELETE');
    request.flush(null, { status: 204, statusText: 'No Content' });
  });

  it('creates object occurrence entries with the revised contract payload', () => {
    service
      .createObjectOccurrenceEntry('project-1', {
        collectionUseObjectId: 'cuo-1',
        numberOfObjects: 1,
        occurrenceDate: '2026-06-03T11:30:00',
        location: 'Conservation lab, room 2',
        detailedDescription: 'Surface abrasion reported during handling.',
        testimonial: 'Observed by the researcher.',
      })
      .subscribe();

    const request = http.expectOne(
      'https://api.example.test/collection-use-projects/project-1/occurrence-entries',
    );

    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual({
      collectionUseObjectId: 'cuo-1',
      numberOfObjects: 1,
      occurrenceDate: '2026-06-03T11:30:00',
      location: 'Conservation lab, room 2',
      detailedDescription: 'Surface abrasion reported during handling.',
      testimonial: 'Observed by the researcher.',
    });
    request.flush({
      id: 'occurrence-1',
      collectionUseObjectId: 'cuo-1',
      objectReference: {
        inventoryNumber: 'INV-001',
        displayTitle: null,
        objectName: null,
        briefDescriptionSnapshot: null,
      },
      numberOfObjects: 1,
      occurrenceDate: '2026-06-03T11:30:00',
      location: 'Conservation lab, room 2',
      reportedBy: {
        permissionId: 'permission-1',
        user: { id: 'user-1', name: 'Ana', email: 'ana@example.test' },
        group: 'COLLECTIONS_MANAGEMENT',
      },
      detailedDescription: 'Surface abrasion reported during handling.',
      testimonial: 'Observed by the researcher.',
      attachments: [],
    });
  });

  it('lists object occurrence entries with reportedBy filters and occurrence log metadata', () => {
    service
      .listObjectOccurrenceEntries('project-1', {
        reportedBy: 'permission-1',
        page: 1,
        size: 10,
      })
      .subscribe();

    const request = http.expectOne(
      'https://api.example.test/collection-use-projects/project-1/occurrence-entries?reportedBy=permission-1&page=1&size=10',
    );

    expect(request.request.method).toBe('GET');
    expect(request.request.params.get('reportedBy')).toBe('permission-1');
    request.flush({
      projectId: 'project-1',
      occurrenceLog: {
        id: 'occurrence-log-1',
        referenceNumber: 'OOL-1A2B3C4D',
        projectId: 'project-1',
        curator: null,
      },
      content: [],
      page: 1,
      size: 10,
      totalElements: 0,
      totalPages: 0,
    });
  });

  it('gets object occurrence logs', () => {
    service.getObjectOccurrenceLog('project-1').subscribe();

    const getRequest = http.expectOne(
      'https://api.example.test/collection-use-projects/project-1/object-occurrence-log',
    );

    expect(getRequest.request.method).toBe('GET');
    getRequest.flush({
      id: 'occurrence-log-1',
      referenceNumber: 'OOL-1A2B3C4D',
      projectId: 'project-1',
      curator: null,
    });
  });

  it('downloads an occurrence entry attachment as a blob', () => {
    let received: Blob | undefined;

    service
      .downloadOccurrenceEntryAttachment('project-1', 'entry-1', 'report-2024.pdf')
      .subscribe((blob) => (received = blob));

    const request = http.expectOne(
      'https://api.example.test/collection-use-projects/project-1/occurrence-entries/entry-1/attachments/report-2024.pdf',
    );

    expect(request.request.method).toBe('GET');
    expect(request.request.responseType).toBe('blob');

    const blob = new Blob(['file-bytes']);
    request.flush(blob);
    expect(received).toBe(blob);
  });

  it('uploads occurrence entry attachments as multipart form data', () => {
    const file = new File(['image'], 'occurrence.jpg', { type: 'image/jpeg' });

    service
      .uploadOccurrenceEntryAttachment('project-1', 'entry-1', file, 'IMAGE', 'Occurrence photo')
      .subscribe();

    const request = http.expectOne(
      'https://api.example.test/collection-use-projects/project-1/occurrence-entries/entry-1/attachments',
    );

    expect(request.request.method).toBe('POST');
    expect(request.request.body instanceof FormData).toBe(true);
    expect((request.request.body as FormData).get('file')).toBe(file);
    expect((request.request.body as FormData).get('mediaType')).toBe('IMAGE');
    expect((request.request.body as FormData).get('attachmentDescription')).toBe(
      'Occurrence photo',
    );
    request.flush({
      fileReference: 'files/occurrence',
      fileName: 'occurrence.jpg',
      mediaType: 'IMAGE',
      uploadedAt: '2026-06-03T10:00:00',
      attachmentDescription: 'Occurrence photo',
    });
  });

  it('deletes an occurrence entry attachment with an encoded file reference', () => {
    service.deleteOccurrenceEntryAttachment('project-1', 'entry-1', 'report 2024.pdf').subscribe();

    const request = http.expectOne(
      'https://api.example.test/collection-use-projects/project-1/occurrence-entries/entry-1/attachments/report%202024.pdf',
    );

    expect(request.request.method).toBe('DELETE');
    request.flush(null, { status: 204, statusText: 'No Content' });
  });

  it('creates and lists publication entries with the publication log header', () => {
    service.createPublicationEntry('project-1', { note: 'Published an article.' }).subscribe();
    const createRequest = http.expectOne(
      'https://api.example.test/collection-use-projects/project-1/publication-entries',
    );
    expect(createRequest.request.method).toBe('POST');
    expect(createRequest.request.body).toEqual({ note: 'Published an article.' });
    createRequest.flush({
      id: 'pub-entry-1',
      addedAt: '2026-06-10T14:00:00',
      addedBy: {
        permissionId: 'perm-1',
        user: { id: 'u1', name: 'Ana', email: 'ana@example.test' },
        group: 'EXTERNAL',
      },
      note: 'Published an article.',
      attachments: [],
    });

    service.listPublicationEntries('project-1', { addedBy: 'perm-1' }).subscribe();
    const listRequest = http.expectOne(
      'https://api.example.test/collection-use-projects/project-1/publication-entries?addedBy=perm-1',
    );
    expect(listRequest.request.method).toBe('GET');
    listRequest.flush({
      projectId: 'project-1',
      publicationLog: {
        id: 'pub-1',
        referenceNumber: 'PUB-1A2B3C4D',
        projectId: 'project-1',
        curator: null,
      },
      content: [],
      page: 0,
      size: 20,
      totalElements: 0,
      totalPages: 0,
    });
  });

  it('updates a publication entry note and gets the publication log', () => {
    service.updatePublicationEntry('project-1', 'pub-entry-1', { note: 'fixed' }).subscribe();
    const patchRequest = http.expectOne(
      'https://api.example.test/collection-use-projects/project-1/publication-entries/pub-entry-1',
    );
    expect(patchRequest.request.method).toBe('PATCH');
    expect(patchRequest.request.body).toEqual({ note: 'fixed' });
    patchRequest.flush({
      id: 'pub-entry-1',
      addedAt: '2026-06-10T14:00:00',
      addedBy: {
        permissionId: 'perm-1',
        user: { id: 'u1', name: 'Ana', email: 'ana@example.test' },
        group: 'EXTERNAL',
      },
      note: 'fixed',
      attachments: [],
    });

    service.getPublicationLog('project-1').subscribe();
    const logRequest = http.expectOne(
      'https://api.example.test/collection-use-projects/project-1/publication-log',
    );
    expect(logRequest.request.method).toBe('GET');
    logRequest.flush({
      id: 'pub-1',
      referenceNumber: 'PUB-1A2B3C4D',
      projectId: 'project-1',
      curator: null,
    });
  });

  it('downloads the publication register as a DOCX blob', () => {
    let received: Blob | undefined;
    service.downloadPublicationLogDocument('project-1').subscribe((blob) => (received = blob));

    const request = http.expectOne(
      'https://api.example.test/collection-use-projects/project-1/publication-log/document',
    );
    expect(request.request.method).toBe('GET');
    expect(request.request.responseType).toBe('blob');

    const blob = new Blob(['docx-bytes']);
    request.flush(blob);
    expect(received).toBe(blob);
  });

  it('deletes a publication entry', () => {
    service.deletePublicationEntry('project-1', 'pub-entry-1').subscribe();

    const request = http.expectOne(
      'https://api.example.test/collection-use-projects/project-1/publication-entries/pub-entry-1',
    );
    expect(request.request.method).toBe('DELETE');
    request.flush(null, { status: 204, statusText: 'No Content' });
  });

  it('uploads a publication entry attachment with a required description', () => {
    const file = new File(['pdf'], 'paper.pdf', { type: 'application/pdf' });

    service
      .uploadPublicationEntryAttachment('project-1', 'pub-entry-1', file, 'DOCUMENT', 'The paper')
      .subscribe();

    const request = http.expectOne(
      'https://api.example.test/collection-use-projects/project-1/publication-entries/pub-entry-1/attachments',
    );
    expect(request.request.method).toBe('POST');
    expect(request.request.body instanceof FormData).toBe(true);
    expect((request.request.body as FormData).get('file')).toBe(file);
    expect((request.request.body as FormData).get('mediaType')).toBe('DOCUMENT');
    expect((request.request.body as FormData).get('attachmentDescription')).toBe('The paper');
    request.flush({
      fileReference: 'files/paper',
      fileName: 'paper.pdf',
      mediaType: 'DOCUMENT',
      uploadedAt: '2026-06-10T14:05:00',
      attachmentDescription: 'The paper',
    });
  });

  it('downloads a publication entry attachment as a blob with an encoded file reference', () => {
    let received: Blob | undefined;

    service
      .downloadPublicationEntryAttachment('project-1', 'pub-entry-1', 'paper 2024.pdf')
      .subscribe((blob) => (received = blob));

    const request = http.expectOne(
      'https://api.example.test/collection-use-projects/project-1/publication-entries/pub-entry-1/attachments/paper%202024.pdf',
    );
    expect(request.request.method).toBe('GET');
    expect(request.request.responseType).toBe('blob');

    const blob = new Blob(['file-bytes']);
    request.flush(blob);
    expect(received).toBe(blob);
  });

  it('deletes a publication entry attachment with an encoded file reference', () => {
    service
      .deletePublicationEntryAttachment('project-1', 'pub-entry-1', 'paper 2024.pdf')
      .subscribe();

    const request = http.expectOne(
      'https://api.example.test/collection-use-projects/project-1/publication-entries/pub-entry-1/attachments/paper%202024.pdf',
    );

    expect(request.request.method).toBe('DELETE');
    request.flush(null, { status: 204, statusText: 'No Content' });
  });

  it('calls project TODO item endpoints', () => {
    service.listMyTodoPostits({ completed: false, page: 0, size: 12 }).subscribe();
    const postitsRequest = http.expectOne(
      'https://api.example.test/collection-use-projects/my-todo-items?completed=false&page=0&size=12',
    );
    expect(postitsRequest.request.method).toBe('GET');
    postitsRequest.flush({ items: [] });

    service.listTodoItems('project-1').subscribe();
    const listRequest = http.expectOne(
      'https://api.example.test/collection-use-projects/project-1/todo-items',
    );
    expect(listRequest.request.method).toBe('GET');
    listRequest.flush({ projectId: 'project-1', items: [] });

    service.createTodoItem('project-1', { text: 'Confirm handling conditions' }).subscribe();
    const createRequest = http.expectOne(
      'https://api.example.test/collection-use-projects/project-1/todo-items',
    );
    expect(createRequest.request.method).toBe('POST');
    expect(createRequest.request.body).toEqual({ text: 'Confirm handling conditions' });
    createRequest.flush({
      id: 'todo-1',
      projectId: 'project-1',
      text: 'Confirm handling conditions',
      completed: false,
      createdAt: '2026-08-11T10:00:00Z',
      updatedAt: '2026-08-11T10:00:00Z',
      completedAt: null,
      position: 10,
    });

    service.updateTodoItem('project-1', 'todo-1', { text: 'Confirm conservation' }).subscribe();
    const updateRequest = http.expectOne(
      'https://api.example.test/collection-use-projects/project-1/todo-items/todo-1',
    );
    expect(updateRequest.request.method).toBe('PATCH');
    expect(updateRequest.request.body).toEqual({ text: 'Confirm conservation' });
    updateRequest.flush({
      id: 'todo-1',
      projectId: 'project-1',
      text: 'Confirm conservation',
      completed: false,
      createdAt: '2026-08-11T10:00:00Z',
      updatedAt: '2026-08-11T10:01:00Z',
      completedAt: null,
      position: 10,
    });

    service.completeTodoItem('project-1', 'todo-1').subscribe();
    const completeRequest = http.expectOne(
      'https://api.example.test/collection-use-projects/project-1/todo-items/todo-1/complete',
    );
    expect(completeRequest.request.method).toBe('POST');
    completeRequest.flush({
      id: 'todo-1',
      projectId: 'project-1',
      text: 'Confirm conservation',
      completed: true,
      createdAt: '2026-08-11T10:00:00Z',
      updatedAt: '2026-08-11T10:02:00Z',
      completedAt: '2026-08-11T10:02:00Z',
      position: 10,
    });

    service.reopenTodoItem('project-1', 'todo-1').subscribe();
    const reopenRequest = http.expectOne(
      'https://api.example.test/collection-use-projects/project-1/todo-items/todo-1/reopen',
    );
    expect(reopenRequest.request.method).toBe('POST');
    reopenRequest.flush({
      id: 'todo-1',
      projectId: 'project-1',
      text: 'Confirm conservation',
      completed: false,
      createdAt: '2026-08-11T10:00:00Z',
      updatedAt: '2026-08-11T10:03:00Z',
      completedAt: null,
      position: 10,
    });

    service.deleteTodoItem('project-1', 'todo-1').subscribe();
    const deleteRequest = http.expectOne(
      'https://api.example.test/collection-use-projects/project-1/todo-items/todo-1',
    );
    expect(deleteRequest.request.method).toBe('DELETE');
    deleteRequest.flush(null, { status: 204, statusText: 'No Content' });
  });
});
