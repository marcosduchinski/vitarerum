import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { of } from 'rxjs';
import { vi } from 'vitest';

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
  attachmentCount: 0,
};

class ServiceStub {
  readonly listCalls: MuseumQuestionListQuery[] = [];

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
}

describe('MuseumQuestionsPageComponent', () => {
  let fixture: ComponentFixture<MuseumQuestionsPageComponent>;
  let service: ServiceStub;

  async function setup(): Promise<HTMLElement> {
    service = new ServiceStub();
    await TestBed.configureTestingModule({
      imports: [MuseumQuestionsPageComponent],
      providers: [
        provideRouter([]),
        { provide: MUSEUM_QUESTION_MANAGEMENT_SERVICE, useValue: service },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(MuseumQuestionsPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  it('lists submitted questions by default', async () => {
    const el = await setup();
    expect(el.textContent).toContain('Visit question');
    expect(el.textContent).toContain('ana@example.org');
    expect(service.listCalls[0]).toMatchObject({ status: 'SUBMITTED', page: 0, size: 20 });
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

  it('reloads from the first page when the status filter changes', async () => {
    const el = await setup();
    const select = el.querySelector<HTMLSelectElement>('#museum-question-status')!;
    select.value = 'ANSWERED';
    select.dispatchEvent(new Event('change'));
    fixture.detectChanges();
    await fixture.whenStable();

    expect(service.listCalls.at(-1)).toMatchObject({ status: 'ANSWERED', page: 0, size: 20 });
  });

  it('uses the assignments pagination pattern with configurable rows', async () => {
    const el = await setup();
    expect(el.textContent).toContain('1-20 of 45 questions');
    expect(el.textContent).toContain('Page 1 of 3');

    const sizeSelect = el.querySelector<HTMLSelectElement>('#questions-page-size')!;
    sizeSelect.value = '10';
    sizeSelect.dispatchEvent(new Event('change'));
    fixture.detectChanges();
    await fixture.whenStable();

    expect(service.listCalls.at(-1)).toMatchObject({ page: 0, size: 10 });
  });
});

function menuItemByText(text: string): HTMLElement {
  const item = Array.from(
    document.body.querySelectorAll<HTMLElement>('.p-menu a, .p-menu button'),
  ).find((candidate) => candidate.textContent?.trim().includes(text));
  if (!item) throw new Error(`Menu item not found: ${text}`);
  return item;
}
