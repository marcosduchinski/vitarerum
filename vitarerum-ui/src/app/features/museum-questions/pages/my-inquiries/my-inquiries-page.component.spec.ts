import { computed, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of } from 'rxjs';

import { IDENTITY_SERVICE } from '@core/auth/identity.service';
import { IdentitySession } from '@core/auth/models/identity-session.model';
import {
  MuseumQuestionListItem,
  MuseumQuestionListQuery,
  MuseumQuestionPage,
} from '../../models/museum-question.model';
import { MUSEUM_QUESTION_MANAGEMENT_SERVICE } from '../../services/museum-question-management.service';

import { MyInquiriesPageComponent } from './my-inquiries-page.component';

const session = signal<IdentitySession | null>(null);

const QUESTION: MuseumQuestionListItem = {
  id: 'q1',
  requesterName: 'Ana Souza',
  requesterEmail: 'ana@example.org',
  subject: 'Visit question',
  message: 'I would like to visit.',
  status: 'SUBMITTED',
  createdAt: '2026-07-05T10:00:00Z',
  answeredAt: null,
  answeredBy: null,
  answerBody: null,
  answerSentAt: null,
  outOfScopeAt: null,
  outOfScopeBy: null,
  outOfScopeReason: null,
  outOfScopeEmailSentAt: null,
  closedAt: null,
  closedBy: null,
  assignedTo: {
    permissionId: 'perm-carol',
    user: { id: 'u-carol', name: 'Carol Souza', email: 'carol@example.org' },
    group: 'CURATORIAL',
  },
  attachmentCount: 0,
};

class IdentityStub {
  readonly session = session.asReadonly();
  readonly isAuthenticated = computed(() => session() !== null);
  readonly isStaff = computed(() => session()?.group !== 'EXTERNAL');

  getPermissionId(): string | null {
    return (
      session()?.permissions?.find((permission) => permission.group === session()?.group)
        ?.permissionId ?? null
    );
  }
}

class ServiceStub {
  readonly listCalls: MuseumQuestionListQuery[] = [];

  list(query: MuseumQuestionListQuery) {
    this.listCalls.push(query);
    return of<MuseumQuestionPage>({
      content: [QUESTION],
      page: 0,
      size: 100,
      totalElements: 1,
      totalPages: 1,
    });
  }
}

describe('MyInquiriesPageComponent', () => {
  let service: ServiceStub;

  beforeEach(() => {
    session.set({
      accessToken: 'token',
      user: { id: 'u-carol', email: 'carol@example.org', displayName: 'Carol Souza' },
      group: 'CURATORIAL',
      availableGroups: ['CURATORIAL'],
      permissions: [{ permissionId: 'perm-carol', group: 'CURATORIAL' }],
    });
  });

  it('lists submitted enquiries assigned to the active permission', async () => {
    service = new ServiceStub();
    await TestBed.configureTestingModule({
      imports: [MyInquiriesPageComponent],
      providers: [
        provideRouter([]),
        { provide: IDENTITY_SERVICE, useClass: IdentityStub },
        { provide: MUSEUM_QUESTION_MANAGEMENT_SERVICE, useValue: service },
      ],
    }).compileComponents();

    const fixture = TestBed.createComponent(MyInquiriesPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.textContent).toContain('My enquiries');
    expect(compiled.textContent).toContain('Visit question');
    expect(service.listCalls[0]).toMatchObject({
      assignedTo: 'perm-carol',
      status: 'SUBMITTED',
      page: 0,
      size: 100,
    });
  });
});
