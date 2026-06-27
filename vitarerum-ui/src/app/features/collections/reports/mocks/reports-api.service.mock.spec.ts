import { computed, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { IDENTITY_SERVICE, IdentityService } from '@core/auth/identity.service';
import { GroupName } from '@core/auth/models/group-name.enum';
import { IdentitySession } from '@core/auth/models/identity-session.model';
import { LoginRequest } from '@core/auth/models/login.model';
import { firstValueFrom } from 'rxjs';

import {
  MOCK_SEED,
  MockProjectState,
  TEST_SEED,
} from '@features/collections/proposals/mocks/mock-data';

import { ReportsApiServiceMock } from './reports-api.service.mock';
import { CreateInSituVisitReportRequest } from '../models/report.model';

const STAFF_SESSION: IdentitySession = {
  accessToken: 'token',
  user: { id: 'staff-1', email: 'bob@example.test', displayName: 'Bob Santos' },
  group: 'COLLECTIONS_MANAGEMENT',
  availableGroups: ['COLLECTIONS_MANAGEMENT'],
  permissions: [{ permissionId: 'perm-bob', group: 'COLLECTIONS_MANAGEMENT' }],
};

const EXTERNAL_SESSION: IdentitySession = {
  accessToken: 'token',
  user: { id: 'user-1', email: 'alice@example.test', displayName: 'Alice Ferreira' },
  group: 'EXTERNAL',
  availableGroups: ['EXTERNAL'],
  permissions: [{ permissionId: 'perm-alice', group: 'EXTERNAL' }],
};

let activeSession: IdentitySession = STAFF_SESSION;

class IdentityServiceStub implements IdentityService {
  private readonly sessionState = signal<IdentitySession | null>(activeSession);

  readonly session = this.sessionState.asReadonly();
  readonly isAuthenticated = signal(true).asReadonly();
  readonly isStaff = computed(() => {
    const group = this.session()?.group;
    return group != null && group !== 'EXTERNAL';
  });

  async signIn(credentials: LoginRequest): Promise<void> {
    const session = this.sessionState();
    if (session) {
      this.sessionState.set({ ...session, user: { ...session.user, email: credentials.email } });
    }
  }

  signOut(): void {
    this.sessionState.set(null);
  }

  getAccessToken(): string | null {
    return this.session()?.accessToken ?? null;
  }

  getPermissionId(): string | null {
    const session = this.sessionState();
    return (
      session?.permissions?.find((permission) => permission.group === session.group)
        ?.permissionId ?? null
    );
  }

  setGroup(group: GroupName): void {
    const session = this.sessionState();
    if (session) this.sessionState.set({ ...session, group });
  }

  updateAvailableGroups(groups: readonly GroupName[]): void {
    const session = this.sessionState();
    if (session) this.sessionState.set({ ...session, availableGroups: [...groups] });
  }
}

describe('ReportsApiServiceMock', () => {
  let service: ReportsApiServiceMock;

  beforeEach(() => {
    activeSession = STAFF_SESSION;
    TestBed.configureTestingModule({
      providers: [
        { provide: MOCK_SEED, useValue: TEST_SEED },
        MockProjectState,
        ReportsApiServiceMock,
        { provide: IDENTITY_SERVICE, useClass: IdentityServiceStub },
      ],
    });

    service = TestBed.inject(ReportsApiServiceMock);
  });

  it('returns an empty report history before a report is generated', async () => {
    const page = await firstValueFrom(service.listInSituVisitReports({ size: 20 }));

    expect(page).toMatchObject({
      content: [],
      page: 0,
      size: 20,
      totalElements: 0,
      totalPages: 0,
    });
  });

  it('lists generated reports newest first with pagination', async () => {
    const first = await firstValueFrom(service.createInSituVisitReport('proj-7', validRequest()));
    const second = await firstValueFrom(
      service.createInSituVisitReport('proj-7', {
        ...validRequest(),
        narrativeType: 'scientific',
      }),
    );
    const page = await firstValueFrom(service.listInSituVisitReports({ page: 0, size: 1 }));

    expect(page).toMatchObject({
      content: [second],
      page: 0,
      size: 1,
      totalElements: 2,
      totalPages: 2,
    });
    expect(page.content[0]).toMatchObject({
      code: 'CUP-0002',
      visitorName: 'Hugo Andrade',
      placeName: 'MUHNAC',
      visitBeginDate: '2026-06-01',
      visitEndDate: '2026-06-05',
    });
    expect(second.createdAt > first.createdAt).toBe(true);
  });

  it('rejects non-staff access', async () => {
    activeSession = EXTERNAL_SESSION;
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      providers: [
        { provide: MOCK_SEED, useValue: TEST_SEED },
        MockProjectState,
        ReportsApiServiceMock,
        { provide: IDENTITY_SERVICE, useClass: IdentityServiceStub },
      ],
    });
    service = TestBed.inject(ReportsApiServiceMock);

    await expect(firstValueFrom(service.listInSituVisitReports())).rejects.toMatchObject({
      status: 403,
      error: 'ACCESS_DENIED',
    });
  });

  it('creates append-only in-situ visit reports', async () => {
    const first = await firstValueFrom(
      service.createInSituVisitReport('proj-7', {
        targetLanguage: 'pt',
        narrativeType: 'institutional',
        creativityTemperature: 0.3,
      }),
    );
    const second = await firstValueFrom(
      service.createInSituVisitReport('proj-7', {
        targetLanguage: 'en',
        narrativeType: 'scientific',
        creativityTemperature: 0.7,
      }),
    );

    expect(first).toMatchObject({
      createdBy: 'perm-bob',
      projectId: 'proj-7',
    });
    expect(second).toMatchObject({
      createdBy: 'perm-bob',
      projectId: 'proj-7',
    });
    expect(second.id).not.toBe(first.id);
    expect(second.narrativeId).not.toBe(first.narrativeId);
    expect(second.inSituVisitRecordId).not.toBe(first.inSituVisitRecordId);
  });

  it('returns the generated report detail for its owning project', async () => {
    const report = await firstValueFrom(
      service.createInSituVisitReport('proj-7', {
        targetLanguage: 'en',
        narrativeType: 'scientific',
        creativityTemperature: 0.6,
      }),
    );

    const detail = await firstValueFrom(service.getInSituVisitReportDetail('proj-7', report.id));

    expect(detail).toMatchObject({
      id: report.id,
      narrative: {
        text: expect.stringContaining('Photographic history'),
        meta: {
          resolvedNarrativeType: 'scientific',
          targetLanguage: 'en',
          creativityTemperature: 0.6,
        },
      },
      record: {
        code: 'CUP-0001',
        visitorName: 'Hugo Andrade',
        placeName: 'MUHNAC',
        requestedObjects: [{ sourceId: 'VR-2026-007' }],
      },
    });
  });

  it('returns a CIDOC-CRM JSON-LD document for a generated record', async () => {
    const report = await firstValueFrom(service.createInSituVisitReport('proj-7', validRequest()));

    const document = await firstValueFrom(
      service.getInSituVisitCidocCrm(report.inSituVisitRecordId),
    );

    expect(document).toMatchObject({
      '@context': { crm: 'http://www.cidoc-crm.org/cidoc-crm/' },
      '@graph': [
        {
          '@id': `ex:visit/${report.inSituVisitRecordId}`,
          '@type': 'crm:E7_Activity',
        },
      ],
    });
  });

  it('updates only the narrative text and persists the trimmed result', async () => {
    const report = await firstValueFrom(service.createInSituVisitReport('proj-7', validRequest()));
    const before = await firstValueFrom(service.getInSituVisitReportDetail('proj-7', report.id));

    const updated = await firstValueFrom(
      service.updateInSituVisitNarrative(report.inSituVisitRecordId, report.narrativeId, {
        narrative: '  Corrected narrative text.  ',
      }),
    );
    const after = await firstValueFrom(service.getInSituVisitReportDetail('proj-7', report.id));

    expect(updated.text).toBe('Corrected narrative text.');
    expect(after.narrative).toEqual(updated);
    expect(updated.meta).toEqual(before.narrative?.meta);
    expect(updated.generatedAt).toBe(before.narrative?.generatedAt);
  });

  it('rejects missing CIDOC-CRM records, narrative mismatches, and blank edits', async () => {
    const report = await firstValueFrom(service.createInSituVisitReport('proj-7', validRequest()));

    await expect(
      firstValueFrom(service.getInSituVisitCidocCrm('missing-record')),
    ).rejects.toMatchObject({ status: 404, error: 'IN_SITU_VISIT_NOT_FOUND' });
    await expect(
      firstValueFrom(
        service.updateInSituVisitNarrative(report.inSituVisitRecordId, 'missing-narrative', {
          narrative: 'Valid replacement',
        }),
      ),
    ).rejects.toMatchObject({ status: 404, error: 'NARRATIVE_NOT_FOUND' });
    await expect(
      firstValueFrom(
        service.updateInSituVisitNarrative(report.inSituVisitRecordId, report.narrativeId, {
          narrative: '   ',
        }),
      ),
    ).rejects.toMatchObject({ status: 422, error: 'VALIDATION_ERROR' });
  });

  it('rejects non-staff CIDOC-CRM and narrative access', async () => {
    activeSession = EXTERNAL_SESSION;
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      providers: [
        { provide: MOCK_SEED, useValue: TEST_SEED },
        MockProjectState,
        ReportsApiServiceMock,
        { provide: IDENTITY_SERVICE, useClass: IdentityServiceStub },
      ],
    });
    service = TestBed.inject(ReportsApiServiceMock);

    await expect(firstValueFrom(service.getInSituVisitCidocCrm('record-1'))).rejects.toMatchObject({
      status: 403,
      error: 'ACCESS_DENIED',
    });
    await expect(
      firstValueFrom(
        service.updateInSituVisitNarrative('record-1', 'narrative-1', {
          narrative: 'Corrected narrative',
        }),
      ),
    ).rejects.toMatchObject({ status: 403, error: 'ACCESS_DENIED' });
  });

  it('rejects missing reports and project/report ownership mismatches', async () => {
    const report = await firstValueFrom(service.createInSituVisitReport('proj-7', validRequest()));

    await expect(
      firstValueFrom(service.getInSituVisitReportDetail('proj-6', report.id)),
    ).rejects.toMatchObject({ status: 404, error: 'REPORT_NOT_FOUND' });
    await expect(
      firstValueFrom(service.getInSituVisitReportDetail('proj-7', 'missing-report')),
    ).rejects.toMatchObject({ status: 404, error: 'REPORT_NOT_FOUND' });
  });

  it.each([
    ['missing project', 'missing-project', validRequest(), 404, 'PROJECT_NOT_FOUND'],
    ['wrong use type', 'proj-5', validRequest(), 409, 'INVALID_USE_TYPE'],
    [
      'invalid language',
      'proj-7',
      { ...validRequest(), targetLanguage: 'fr' } as unknown as CreateInSituVisitReportRequest,
      400,
      'INVALID_TARGET_LANGUAGE',
    ],
    [
      'invalid narrative type',
      'proj-7',
      {
        ...validRequest(),
        narrativeType: 'marketing',
      } as unknown as CreateInSituVisitReportRequest,
      400,
      'INVALID_NARRATIVE_TYPE',
    ],
    [
      'invalid temperature',
      'proj-7',
      { ...validRequest(), creativityTemperature: 1.1 },
      400,
      'INVALID_CREATIVITY_TEMPERATURE',
    ],
  ] as const)(
    'rejects %s when creating a report',
    async (_label, projectId, request, status, error) => {
      await expect(
        firstValueFrom(service.createInSituVisitReport(projectId, request)),
      ).rejects.toMatchObject({ status, error });
    },
  );
});

function validRequest(): CreateInSituVisitReportRequest {
  return {
    targetLanguage: 'pt',
    narrativeType: 'institutional',
    creativityTemperature: 0.3,
  };
}
