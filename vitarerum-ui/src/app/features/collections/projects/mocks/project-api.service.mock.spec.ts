import { computed, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { firstValueFrom } from 'rxjs';

import { IDENTITY_SERVICE } from '@core/auth/identity.service';
import { IdentitySession } from '@core/auth/models/identity-session.model';
import { MOCK_SEED, MockProjectState, TEST_SEED } from '../../proposals/mocks/mock-data';
import { ProjectApiServiceMock } from './project-api.service.mock';

describe('ProjectApiServiceMock', () => {
  let service: ProjectApiServiceMock;
  let state: MockProjectState;
  let session: ReturnType<typeof signal<IdentitySession>>;

  beforeEach(() => {
    session = signal(externalSession());

    TestBed.configureTestingModule({
      providers: [
        ProjectApiServiceMock,
        MockProjectState,
        { provide: MOCK_SEED, useValue: TEST_SEED },
        {
          provide: IDENTITY_SERVICE,
          useValue: {
            session: session.asReadonly(),
            isAuthenticated: signal(true).asReadonly(),
            isStaff: computed(() => {
              const group = session()?.group;
              return group != null && group !== 'EXTERNAL';
            }),
            signIn: () => Promise.resolve(),
            signOut: () => void session(),
            getAccessToken: () => 'mock-token',
            getPermissionId: () => {
              const id = session()?.user.id;
              return id ? `perm-${id.replace(/^u-/, '')}` : null;
            },
            setGroup: (group: IdentitySession['group']) => void group,
            updateAvailableGroups: (groups: IdentitySession['availableGroups']) =>
              void groups.length,
          },
        },
      ],
    });

    service = TestBed.inject(ProjectApiServiceMock);
    state = TestBed.inject(MockProjectState);
  });

  it('returns seeded projects on list', async () => {
    const page = await firstValueFrom(service.listProjects());
    expect(page.totalElements).toBeGreaterThan(0);
  });

  it('returns researcher project detail actions without staff context', async () => {
    const detail = await firstValueFrom(service.getProject('proj-4'));

    expect(detail.actions).toMatchObject({
      canStart: true,
      canComplete: false,
      canCancel: true,
      canOpenLog: false,
      canCreateObjectLogEntry: false,
      canCreateOccurrenceEntry: false,
    });
    expect(detail.staffContext).toBeNull();
  });

  it('returns staff project detail context from seeded proposal data', async () => {
    session.set(staffSession());

    const detail = await firstValueFrom(service.getProject('proj-4'));

    expect(detail.actions).toMatchObject({
      canStart: false,
      canCancel: true,
      canOpenLog: true,
      canCreateObjectLogEntry: true,
      canCreateOccurrenceEntry: true,
    });
    expect(detail.staffContext?.viewerGroup).toBe('COLLECTIONS_MANAGEMENT');
    expect(detail.staffContext?.proposal).toMatchObject({
      id: 'prop-4',
      referenceNumber: 'VRP-20260601-0004',
      submittedBy: { permissionId: 'perm-alice' },
      assignedTo: { permissionId: 'perm-bob' },
    });
    expect(detail.staffContext?.documents.map((document) => document.fileName)).toContain(
      'laboratory-instruments-exhibition-brief.pdf',
    );
    expect(detail.staffContext?.conversationSummary).toMatchObject({
      conversationId: 'conv-4',
      totalMessages: 1,
      lastMessageBy: { permissionId: 'perm-alice' },
    });
    expect(detail.staffContext?.logSummary).toMatchObject({
      accessLog: null,
      occurrenceLog: null,
      objectLogEntryCount: 0,
      occurrenceEntryCount: 0,
      attachmentCount: 0,
    });
  });

  it('transitions CREATED → IN_PROGRESS and updates event log', async () => {
    const result = await firstValueFrom(
      service.startProject('proj-4', { note: 'Starting access.' }),
    );
    expect(result.status).toBe('IN_PROGRESS');

    const detail = await firstValueFrom(service.getProject('proj-4'));
    expect(detail.status).toBe('IN_PROGRESS');

    const events = await firstValueFrom(service.listEvents('proj-4'));
    const last = events.content[events.content.length - 1];
    expect(last.type).toBe('STARTED');
  });

  it('rejects starting a project that is already in progress', async () => {
    state.projects.get('proj-4')!.status = 'IN_PROGRESS';

    await expect(
      firstValueFrom(service.startProject('proj-4', { note: 'Too early.' })),
    ).rejects.toMatchObject({
      status: 409,
      error: 'INVALID_TRANSITION',
    });
  });

  it('rejects completing a project before it is in progress', async () => {
    await expect(
      firstValueFrom(service.completeProject('proj-4', { note: 'Done too early.' })),
    ).rejects.toMatchObject({
      status: 409,
      error: 'INVALID_TRANSITION',
    });
  });

  it('completes an in-progress project', async () => {
    state.projects.get('proj-4')!.status = 'IN_PROGRESS';

    const completed = await firstValueFrom(
      service.completeProject('proj-4', { note: 'Completed.' }),
    );
    expect(completed.status).toBe('COMPLETED');
  });

  it('creates an object log entry and lists it', async () => {
    state.projects.get('proj-4')!.status = 'IN_PROGRESS';

    const entry = await firstValueFrom(
      service.createObjectLogEntry('proj-4', {
        inventoryNumber: 'INV-001',
        numberOfObjects: 2,
        observations: 'Session note.',
      }),
    );
    expect(entry.id).toBeTruthy();
    expect(entry.objectReference.inventoryNumber).toBe('INV-001');
    expect(entry.numberOfObjects).toBe(2);
    expect(entry.observations).toBe('Session note.');

    const page = await firstValueFrom(service.listObjectLogEntries('proj-4'));
    expect(page.accessLog?.referenceNumber).toMatch(/^OAL-/);
    expect(page.content.some((e) => e.id === entry.id)).toBe(true);
  });

  it('gets the object access log created by the first object entry', async () => {
    state.projects.get('proj-4')!.status = 'IN_PROGRESS';

    await firstValueFrom(
      service.createObjectLogEntry('proj-4', {
        inventoryNumber: 'INV-002',
        numberOfObjects: 1,
      }),
    );

    const accessLog = await firstValueFrom(service.getObjectAccessLog('proj-4'));
    expect(accessLog.projectId).toBe('proj-4');
    expect(accessLog.referenceNumber).toMatch(/^OAL-/);
  });

  it('updates editable object log entry fields', async () => {
    state.projects.get('proj-4')!.status = 'IN_PROGRESS';
    const entry = await firstValueFrom(
      service.createObjectLogEntry('proj-4', {
        inventoryNumber: 'INV-EDIT-001',
        numberOfObjects: 1,
        observations: 'Initial note.',
      }),
    );

    const updated = await firstValueFrom(
      service.updateObjectLogEntry('proj-4', entry.id, {
        addedAt: '2026-06-05T12:30:00Z',
        numberOfObjects: 3,
        observations: null,
      }),
    );

    expect(updated.objectReference.inventoryNumber).toBe('INV-EDIT-001');
    expect(updated.addedBy.permissionId).toBe(entry.addedBy.permissionId);
    expect(updated.addedAt).toBe('2026-06-05T12:30:00Z');
    expect(updated.numberOfObjects).toBe(3);
    expect(updated.observations).toBeNull();

    const page = await firstValueFrom(service.listObjectLogEntries('proj-4'));
    expect(page.content.find((item) => item.id === entry.id)?.numberOfObjects).toBe(3);
  });

  it('rejects object access log lookup before the first object entry', async () => {
    await expect(firstValueFrom(service.getObjectAccessLog('proj-4'))).rejects.toMatchObject({
      status: 404,
      error: 'OBJECT_ACCESS_LOG_NOT_FOUND',
    });
  });

  it('allows staff to create object log entries outside IN_PROGRESS', async () => {
    session.set(staffSession());
    state.projects.get('proj-4')!.status = 'COMPLETED';

    const entry = await firstValueFrom(
      service.createObjectLogEntry('proj-4', {
        inventoryNumber: 'INV-003',
        numberOfObjects: 1,
      }),
    );
    expect(entry.objectReference.inventoryNumber).toBe('INV-003');
  });

  it.each(['CREATED', 'CANCELLED'] as const)(
    'allows staff to create object log entries while project is %s',
    async (status) => {
      session.set(staffSession());
      state.projects.get('proj-4')!.status = status;

      const entry = await firstValueFrom(
        service.createObjectLogEntry('proj-4', {
          inventoryNumber: `INV-ACCESS-${status}`,
          numberOfObjects: 1,
        }),
      );

      expect(entry.addedBy.permissionId).toBe('perm-bob');
      expect(entry.objectReference.inventoryNumber).toBe(`INV-ACCESS-${status}`);
    },
  );

  it('creates an object occurrence entry and lists it', async () => {
    state.projects.get('proj-4')!.status = 'IN_PROGRESS';

    const entry = await firstValueFrom(
      service.createObjectOccurrenceEntry('proj-4', {
        inventoryNumber: 'INV-010',
        numberOfObjects: 1,
        occurrenceDate: '2026-06-03T11:30:00Z',
        location: 'Reading room',
        detailedDescription: 'Occurrence note.',
        testimonial: 'Reported during consultation.',
      }),
    );
    expect(entry.id).toBeTruthy();
    expect(entry.objectReference.inventoryNumber).toBe('INV-010');
    expect(entry.numberOfObjects).toBe(1);
    expect(entry.location).toBe('Reading room');
    expect(entry.reportedBy.permissionId).toBe('perm-alice');
    expect(entry.detailedDescription).toBe('Occurrence note.');
    expect(entry.testimonial).toBe('Reported during consultation.');

    const page = await firstValueFrom(service.listObjectOccurrenceEntries('proj-4'));
    expect(page.occurrenceLog?.referenceNumber).toMatch(/^OOL-/);
    expect(page.content.some((e) => e.id === entry.id)).toBe(true);
  });

  it('gets the object occurrence log created by the first occurrence entry', async () => {
    state.projects.get('proj-4')!.status = 'IN_PROGRESS';

    await firstValueFrom(
      service.createObjectOccurrenceEntry('proj-4', {
        inventoryNumber: 'INV-011',
        numberOfObjects: 1,
        occurrenceDate: '2026-06-04T10:00:00Z',
        location: 'Conservation lab',
        detailedDescription: 'Condition detail recorded.',
      }),
    );

    const occurrenceLog = await firstValueFrom(service.getObjectOccurrenceLog('proj-4'));
    expect(occurrenceLog.projectId).toBe('proj-4');
    expect(occurrenceLog.referenceNumber).toMatch(/^OOL-/);
  });

  it('rejects object occurrence log lookup before the first occurrence entry', async () => {
    await expect(firstValueFrom(service.getObjectOccurrenceLog('proj-4'))).rejects.toMatchObject({
      status: 404,
      error: 'OBJECT_OCCURRENCE_LOG_NOT_FOUND',
    });
  });

  it('filters object occurrence entries by reportedBy', async () => {
    state.projects.get('proj-4')!.status = 'IN_PROGRESS';
    const entry = await firstValueFrom(
      service.createObjectOccurrenceEntry('proj-4', {
        inventoryNumber: 'INV-012',
        numberOfObjects: 1,
        occurrenceDate: '2026-06-04T10:30:00Z',
        location: 'Reading room',
        detailedDescription: 'Reported by external researcher.',
      }),
    );

    const page = await firstValueFrom(
      service.listObjectOccurrenceEntries('proj-4', { reportedBy: 'perm-alice' }),
    );

    expect(page.content).toHaveLength(1);
    expect(page.content[0].id).toBe(entry.id);
  });

  it('allows staff to create object occurrence entries outside IN_PROGRESS', async () => {
    session.set(staffSession());
    state.projects.get('proj-4')!.status = 'COMPLETED';

    const entry = await firstValueFrom(
      service.createObjectOccurrenceEntry('proj-4', {
        inventoryNumber: 'INV-013',
        numberOfObjects: 1,
        occurrenceDate: '2026-06-04T11:00:00Z',
        location: 'Collections office',
        detailedDescription: 'Staff annotation after project completion.',
      }),
    );

    expect(entry.reportedBy.permissionId).toBe('perm-bob');
  });

  it.each(['CREATED', 'CANCELLED'] as const)(
    'allows staff to create object occurrence entries while project is %s',
    async (status) => {
      session.set(staffSession());
      state.projects.get('proj-4')!.status = status;

      const entry = await firstValueFrom(
        service.createObjectOccurrenceEntry('proj-4', {
          inventoryNumber: `INV-OCC-${status}`,
          numberOfObjects: 1,
          occurrenceDate: '2026-06-04T11:00:00Z',
          location: 'Collections office',
          detailedDescription: `Staff occurrence annotation while ${status}.`,
        }),
      );

      expect(entry.reportedBy.permissionId).toBe('perm-bob');
      expect(entry.objectReference.inventoryNumber).toBe(`INV-OCC-${status}`);
    },
  );

  it('rejects researcher occurrence entries outside IN_PROGRESS', async () => {
    state.projects.get('proj-4')!.status = 'COMPLETED';

    await expect(
      firstValueFrom(
        service.createObjectOccurrenceEntry('proj-4', {
          inventoryNumber: 'INV-014',
          numberOfObjects: 1,
          occurrenceDate: '2026-06-04T11:30:00Z',
          location: 'Reading room',
          detailedDescription: 'Should be rejected.',
        }),
      ),
    ).rejects.toMatchObject({
      status: 409,
      error: 'INVALID_TRANSITION',
    });
  });

  it('filters projects by status', async () => {
    session.set(staffSession());
    const page = await firstValueFrom(service.listProjects({ status: 'IN_PROGRESS' }));
    expect(page.content.every((p) => p.status === 'IN_PROGRESS')).toBe(true);
  });

  it('has created project examples for proposals', async () => {
    session.set(staffSession());
    const page = await firstValueFrom(service.listProjects({ status: 'CREATED', size: 20 }));
    expect(page.totalElements).toBeGreaterThan(0);
  });

  it('filters projects to those with proposals assigned to a specific reviewer', async () => {
    session.set(staffSession());
    const page = await firstValueFrom(service.listProjects({ assignedTo: 'perm-bob', size: 20 }));

    expect(page.totalElements).toBeGreaterThan(0);
    expect(page.content.every((p) => p.proposal.assignedTo?.permissionId === 'perm-bob')).toBe(
      true,
    );
  });

  it('scopes a non-staff list to the caller’s own requested projects', async () => {
    // Default session is the external researcher Alice (perm-alice).
    const page = await firstValueFrom(service.listProjects({ size: 20 }));

    expect(page.totalElements).toBeGreaterThan(0);
    expect(page.content.every((p) => p.requestedBy?.permissionId === 'perm-alice')).toBe(true);
  });

  it('ignores requestedBy for a non-staff caller and forces their own id', async () => {
    // Even when an external caller asks for another requester, the list is
    // forced back to their own permissionId.
    const page = await firstValueFrom(service.listProjects({ requestedBy: 'perm-hugo', size: 20 }));

    expect(page.content.every((p) => p.requestedBy?.permissionId === 'perm-alice')).toBe(true);
  });

  it('honors requestedBy for a staff caller', async () => {
    session.set(staffSession());
    const page = await firstValueFrom(service.listProjects({ requestedBy: 'perm-hugo', size: 20 }));

    expect(page.totalElements).toBeGreaterThan(0);
    expect(page.content.every((p) => p.requestedBy?.permissionId === 'perm-hugo')).toBe(true);
  });

  it('downloads an uploaded log entry attachment as a blob', async () => {
    session.set(staffSession());
    const file = new File(['x'], 'evidence.pdf', { type: 'application/pdf' });
    const attachment = await firstValueFrom(
      service.uploadLogEntryAttachment('proj-3', 'entry-101', file, 'DOCUMENT'),
    );

    const blob = await firstValueFrom(
      service.downloadLogEntryAttachment('proj-3', 'entry-101', attachment.fileReference),
    );

    expect(blob).toBeInstanceOf(Blob);
    expect(blob.size).toBeGreaterThan(0);
  });

  it('rejects downloading an unknown log entry attachment with 404', async () => {
    await expect(
      firstValueFrom(service.downloadLogEntryAttachment('proj-3', 'entry-101', 'no-such-ref')),
    ).rejects.toMatchObject({ status: 404, error: 'ATTACHMENT_NOT_FOUND' });
  });

  it('rejects researcher object log entries outside IN_PROGRESS', async () => {
    state.projects.get('proj-4')!.status = 'COMPLETED';

    await expect(
      firstValueFrom(
        service.createObjectLogEntry('proj-4', {
          inventoryNumber: 'INV-004',
          numberOfObjects: 1,
        }),
      ),
    ).rejects.toMatchObject({
      status: 409,
      error: 'INVALID_TRANSITION',
    });
  });

  it('rejects uploadLogEntryAttachment when entry not found', async () => {
    state.projects.get('proj-4')!.status = 'IN_PROGRESS';

    await expect(
      firstValueFrom(
        service.uploadLogEntryAttachment(
          'proj-4',
          'no-such-entry',
          new File(['x'], 'x.jpg'),
          'IMAGE',
        ),
      ),
    ).rejects.toMatchObject({
      status: 404,
      error: 'NOT_FOUND',
    });
  });

  it('filters events by type', async () => {
    await firstValueFrom(service.startProject('proj-4', { note: 'Starting.' }));

    const started = await firstValueFrom(service.listEvents('proj-4', { type: 'STARTED' }));
    expect(started.content.every((e) => e.type === 'STARTED')).toBe(true);

    const pending = await firstValueFrom(service.listEvents('proj-4', { type: 'REQUESTED' }));
    expect(pending.content.every((e) => e.type === 'REQUESTED')).toBe(true);
    expect(pending.content.some((e) => e.type === 'STARTED')).toBe(false);
  });

  it('lets the external requester add publication entries while IN_PROGRESS', async () => {
    await firstValueFrom(service.startProject('proj-4', { note: 'Starting.' }));
    const entry = await firstValueFrom(
      service.createPublicationEntry('proj-4', { note: 'Published a dataset.' }),
    );
    expect(entry.note).toBe('Published a dataset.');
    expect(entry.addedBy.permissionId).toBe('perm-alice');

    const page = await firstValueFrom(service.listPublicationEntries('proj-4'));
    expect(page.content.some((e) => e.id === entry.id)).toBe(true);
    expect(page.publicationLog?.referenceNumber).toMatch(/^PUB-/);
  });

  it('rejects staff publication entries while the project is IN_PROGRESS', async () => {
    const project = state.projects.get('proj-4')!;
    state.projects.set('proj-4', { ...project, status: 'IN_PROGRESS' });
    session.set(curatorialSession());
    await expect(
      firstValueFrom(service.createPublicationEntry('proj-4', { note: 'Staff note.' })),
    ).rejects.toMatchObject({ status: 403, error: 'ACCESS_DENIED' });
  });

  it('lets publication staff add entries once the project is COMPLETED', async () => {
    const project = state.projects.get('proj-4')!;
    state.projects.set('proj-4', { ...project, status: 'COMPLETED' });
    session.set(curatorialSession());

    const entry = await firstValueFrom(
      service.createPublicationEntry('proj-4', { note: 'Catalogued the publication.' }),
    );
    expect(entry.addedBy.permissionId).toBe('perm-carol');
  });

  it('rejects the external requester once the project is COMPLETED', async () => {
    const project = state.projects.get('proj-4')!;
    state.projects.set('proj-4', { ...project, status: 'COMPLETED' });

    await expect(
      firstValueFrom(service.createPublicationEntry('proj-4', { note: 'Late note.' })),
    ).rejects.toMatchObject({ status: 403, error: 'ACCESS_DENIED' });
  });

  it('rejects publication entries for non-active, non-completed projects', async () => {
    const project = state.projects.get('proj-4')!;
    state.projects.set('proj-4', { ...project, status: 'CANCELLED' });

    await expect(
      firstValueFrom(service.createPublicationEntry('proj-4', { note: 'Note.' })),
    ).rejects.toMatchObject({ status: 409, error: 'INVALID_TRANSITION' });
  });

  it('edits a publication entry note and uploads attachments', async () => {
    await firstValueFrom(service.startProject('proj-4', { note: 'Starting.' }));
    const entry = await firstValueFrom(
      service.createPublicationEntry('proj-4', { note: 'Original note.' }),
    );

    const updated = await firstValueFrom(
      service.updatePublicationEntry('proj-4', entry.id, { note: 'Corrected note.' }),
    );
    expect(updated.note).toBe('Corrected note.');

    const file = new File(['pub'], 'publication.pdf', { type: 'application/pdf' });
    const attachment = await firstValueFrom(
      service.uploadPublicationEntryAttachment('proj-4', entry.id, file, 'DOCUMENT', 'The PDF'),
    );
    expect(attachment.note).toBe('The PDF');

    const page = await firstValueFrom(service.listPublicationEntries('proj-4'));
    const stored = page.content.find((e) => e.id === entry.id);
    expect(stored?.attachments.some((a) => a.fileName === 'publication.pdf')).toBe(true);
  });

  it('rejects publication log lookup before the first entry', async () => {
    await expect(firstValueFrom(service.getPublicationLog('proj-4'))).rejects.toMatchObject({
      status: 404,
      error: 'PUBLICATION_LOG_NOT_FOUND',
    });
  });
});

function externalSession(): IdentitySession {
  return {
    accessToken: 'mock-token',
    user: { id: 'u-alice', email: 'alice@ext.example.com', displayName: 'Alice' },
    group: 'EXTERNAL',
    availableGroups: ['EXTERNAL'],
  };
}

function staffSession(): IdentitySession {
  return {
    accessToken: 'mock-token',
    user: { id: 'u-bob', email: 'bob@collections.example.com', displayName: 'Bob' },
    group: 'COLLECTIONS_MANAGEMENT',
    availableGroups: ['COLLECTIONS_MANAGEMENT'],
  };
}

function curatorialSession(): IdentitySession {
  return {
    accessToken: 'mock-token',
    user: { id: 'u-carol', email: 'carol@curatorial.example.com', displayName: 'Carol' },
    group: 'CURATORIAL',
    availableGroups: ['CURATORIAL'],
  };
}
