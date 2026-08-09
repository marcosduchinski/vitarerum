import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, Router, provideRouter } from '@angular/router';
import { of } from 'rxjs';
import { vi } from 'vitest';

import { USER_MANAGEMENT_SERVICE } from '@features/admin/services/user-management.service';
import {
  MuseumQuestionListItem,
  MuseumQuestionListQuery,
  MuseumQuestionPage,
} from '../models/museum-question.model';
import { MUSEUM_QUESTION_MANAGEMENT_SERVICE } from '../services/museum-question-management.service';
import { MuseumQuestionsPageComponent } from './museum-questions-page.component';

const QUESTION: MuseumQuestionListItem = {
  id: 'q1',
  requesterName: 'Ana Souza',
  requesterEmail: 'ana@example.org',
  subject: 'Visit question',
  message: '<b>Please do not render as HTML</b>',
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
  assignedTo: null,
  attachmentCount: 0,
};

class ServiceStub {
  readonly listCalls: MuseumQuestionListQuery[] = [];
  readonly forwardCalls: { questionId: string; targetPermissionId: string }[] = [];

  list(query: MuseumQuestionListQuery) {
    this.listCalls.push(query);
    return of<MuseumQuestionPage>({
      content: [QUESTION],
      page: query.page,
      size: query.size,
      totalElements: 45,
      totalPages: Math.ceil(45 / query.size),
    });
  }

  forward(questionId: string, body: { targetPermissionId: string }) {
    this.forwardCalls.push({ questionId, targetPermissionId: body.targetPermissionId });
    return of({
      ...QUESTION,
      assignedTo: {
        permissionId: 'perm-carol',
        user: { id: 'u-carol', name: 'Carol Souza', email: 'carol@example.org' },
        group: 'CURATORIAL' as const,
      },
      attachments: [],
    });
  }
}

const USER_PAGE = {
  content: [
    {
      id: 'u-carol',
      name: 'Carol Souza',
      email: 'carol@example.org',
      permissions: [
        {
          permissionId: 'perm-carol',
          group: { id: 'group-curatorial', name: 'CURATORIAL' as const },
        },
      ],
    },
  ],
  page: 0,
  size: 100,
  totalElements: 1,
  totalPages: 1,
};

class UserServiceStub {
  listUsers() {
    return of(USER_PAGE);
  }
}

describe('MuseumQuestionsPageComponent', () => {
  let fixture: ComponentFixture<MuseumQuestionsPageComponent>;
  let service: ServiceStub;

  async function setup(mode: 'all' | 'new' = 'all'): Promise<HTMLElement> {
    service = new ServiceStub();
    await TestBed.configureTestingModule({
      imports: [MuseumQuestionsPageComponent],
      providers: [
        provideRouter([]),
        {
          provide: ActivatedRoute,
          useValue: { snapshot: { data: { museumQuestionListMode: mode } } },
        },
        { provide: MUSEUM_QUESTION_MANAGEMENT_SERVICE, useValue: service },
        { provide: USER_MANAGEMENT_SERVICE, useClass: UserServiceStub },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(MuseumQuestionsPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  it('lists all enquiries on the default route', async () => {
    const el = await setup();
    expect(el.textContent).toContain('All enquiries');
    expect(el.textContent).toContain('Visit question');
    expect(el.textContent).toContain('ana@example.org');
    expect(service.listCalls[0]).toMatchObject({
      status: 'SUBMITTED',
      page: 0,
      size: 20,
    });
    expect(service.listCalls[0].unassignedOnly).toBe(false);
  });

  it('filters the default all enquiries route by status', async () => {
    const el = await setup();
    const select = el.querySelector<HTMLSelectElement>('#museum-question-status')!;
    select.value = 'ANSWERED';
    select.dispatchEvent(new Event('change'));
    fixture.detectChanges();
    await fixture.whenStable();

    expect(service.listCalls.at(-1)).toMatchObject({
      status: 'ANSWERED',
      page: 0,
      size: 20,
    });
  });

  it('lists only unassigned submitted questions on the new inquiries route', async () => {
    const el = await setup('new');
    expect(el.textContent).toContain('New inquiries');
    expect(el.querySelector('#museum-question-status')).toBeNull();
    expect(service.listCalls[0]).toMatchObject({
      status: 'SUBMITTED',
      unassignedOnly: true,
      page: 0,
      size: 20,
    });
  });

  it('links each question to its detail page', async () => {
    const el = await setup();
    const link = el.querySelector<HTMLAnchorElement>('a[href="/p/museum-questions/q1"]');
    expect(link?.textContent).toContain('Visit question');
  });

  it('shows details in the row actions menu', async () => {
    const el = await setup();
    const navigateSpy = vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
    el.querySelector<HTMLButtonElement>('button[aria-haspopup="menu"]')!.click();
    fixture.detectChanges();

    menuItemByText('Details').click();

    expect(navigateSpy).toHaveBeenCalledWith(['/p/museum-questions', 'q1']);
  });

  it('forwards a submitted question from the row actions menu', async () => {
    const el = await setup('new');
    el.querySelector<HTMLButtonElement>('button[aria-haspopup="menu"]')!.click();
    fixture.detectChanges();

    menuItemByText('Forward').click();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const select = el.querySelector<HTMLSelectElement>('#forward-modal-target')!;
    select.value = 'perm-carol';
    select.dispatchEvent(new Event('change'));
    fixture.detectChanges();

    buttonByText(el, 'Forward').click();
    fixture.detectChanges();
    await fixture.whenStable();

    expect(service.forwardCalls).toEqual([{ questionId: 'q1', targetPermissionId: 'perm-carol' }]);
  });

  it('uses the assignments pagination pattern with configurable rows', async () => {
    const el = await setup('new');
    expect(el.textContent).toContain('1-20 of 45 questions');
    expect(el.textContent).toContain('Page 1 of 3');

    const sizeSelect = el.querySelector<HTMLSelectElement>('#questions-page-size')!;
    sizeSelect.value = '10';
    sizeSelect.dispatchEvent(new Event('change'));
    fixture.detectChanges();
    await fixture.whenStable();

    expect(service.listCalls.at(-1)).toMatchObject({
      status: 'SUBMITTED',
      unassignedOnly: true,
      page: 0,
      size: 10,
    });
  });
});

function menuItemByText(text: string): HTMLElement {
  const item = Array.from(
    document.body.querySelectorAll<HTMLElement>('.p-menu a, .p-menu button'),
  ).find((candidate) => candidate.textContent?.trim().includes(text));
  if (!item) throw new Error(`Menu item not found: ${text}`);
  return item;
}

function buttonByText(root: HTMLElement, text: string): HTMLButtonElement {
  const button = Array.from(root.querySelectorAll('button')).find(
    (candidate) => candidate.textContent?.trim() === text,
  );
  if (!(button instanceof HTMLButtonElement)) throw new Error(`Button not found: ${text}`);
  return button;
}
