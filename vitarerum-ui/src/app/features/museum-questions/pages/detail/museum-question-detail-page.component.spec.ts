import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of } from 'rxjs';

import {
  MuseumQuestion,
  MuseumQuestionListQuery,
  MuseumQuestionPage,
} from '../../models/museum-question.model';
import { MUSEUM_QUESTION_MANAGEMENT_SERVICE } from '../../services/museum-question-management.service';
import { MuseumQuestionDetailPageComponent } from './museum-question-detail-page.component';

const QUESTION: MuseumQuestion = {
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
};

const PREVIOUS_QUESTION: MuseumQuestion = {
  ...QUESTION,
  id: 'q-previous',
  subject: 'Previous collections visit',
  message: 'Did the museum previously allow visits to the archives?',
  status: 'ANSWERED',
  createdAt: '2026-06-22T09:30:00Z',
  answeredAt: '2026-06-22T15:00:00Z',
  answeredBy: 'perm-staff',
  answerBody: 'Yes. Please coordinate the visit with the collections team.',
  answerSentAt: '2026-06-22T15:00:00Z',
};

const OTHER_REQUESTER_QUESTION: MuseumQuestion = {
  ...QUESTION,
  id: 'q-other',
  requesterEmail: 'other@example.org',
  subject: 'Different requester',
  message: 'This should not appear in Ana history.',
  createdAt: '2026-06-20T09:30:00Z',
};

class ServiceStub {
  question = QUESTION;
  historyQuestions: MuseumQuestion[] = [PREVIOUS_QUESTION, OTHER_REQUESTER_QUESTION];
  readonly listCalls: MuseumQuestionListQuery[] = [];
  readonly answerCalls: [string, string][] = [];
  readonly outOfScopeCalls: [string, string | null][] = [];
  readonly closeCalls: string[] = [];

  get() {
    return of(this.question);
  }

  list(query: MuseumQuestionListQuery) {
    this.listCalls.push(query);
    const filtered = [this.question, ...this.historyQuestions]
      .filter((item) => !query.status || item.status === query.status)
      .filter(
        (item) =>
          !query.requesterEmail ||
          item.requesterEmail.toLowerCase() === query.requesterEmail.trim().toLowerCase(),
      )
      .sort((a, b) => a.createdAt.localeCompare(b.createdAt));
    const page: MuseumQuestionPage = {
      content: filtered.slice(query.page * query.size, query.page * query.size + query.size),
      page: query.page,
      size: query.size,
      totalElements: filtered.length,
      totalPages: filtered.length === 0 ? 0 : Math.ceil(filtered.length / query.size),
    };
    return of(page);
  }

  answer(questionId: string, body: { answerBody: string }) {
    this.answerCalls.push([questionId, body.answerBody]);
    this.question = {
      ...this.question,
      status: 'ANSWERED',
      answerBody: body.answerBody,
      answeredAt: '2026-07-05T12:00:00Z',
      answeredBy: 'perm-staff',
      answerSentAt: '2026-07-05T12:00:00Z',
    };
    return of(this.question);
  }

  markOutOfScope(questionId: string, body: { reason: string | null }) {
    this.outOfScopeCalls.push([questionId, body.reason]);
    this.question = {
      ...this.question,
      status: 'OUT_OF_SCOPE',
      outOfScopeReason: body.reason,
      outOfScopeAt: '2026-07-05T12:00:00Z',
      outOfScopeBy: 'perm-staff',
      outOfScopeEmailSentAt: '2026-07-05T12:00:00Z',
    };
    return of(this.question);
  }

  close(questionId: string) {
    this.closeCalls.push(questionId);
    this.question = {
      ...this.question,
      status: 'CLOSED',
      closedAt: '2026-07-05T12:00:00Z',
      closedBy: 'perm-staff',
    };
    return of(this.question);
  }
}

describe('MuseumQuestionDetailPageComponent', () => {
  let fixture: ComponentFixture<MuseumQuestionDetailPageComponent>;
  let service: ServiceStub;

  async function setup(
    question: MuseumQuestion = QUESTION,
    historyQuestions: MuseumQuestion[] = [PREVIOUS_QUESTION, OTHER_REQUESTER_QUESTION],
    tab?: string,
  ): Promise<HTMLElement> {
    service = new ServiceStub();
    service.question = question;
    service.historyQuestions = historyQuestions;
    await TestBed.configureTestingModule({
      imports: [MuseumQuestionDetailPageComponent],
      providers: [
        provideRouter([]),
        { provide: MUSEUM_QUESTION_MANAGEMENT_SERVICE, useValue: service },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(MuseumQuestionDetailPageComponent);
    fixture.componentRef.setInput('id', question.id);
    if (tab) fixture.componentRef.setInput('tab', tab);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  it('renders message detail and keeps citizen content as text', async () => {
    const el = await setup();
    expect(el.textContent).toContain('Visit question');
    expect(el.textContent).toContain('Ana Souza');
    expect(el.textContent).toContain('ana@example.org');
    expect(el.textContent).toContain('<b>Please do not render as HTML</b>');
    expect(el.querySelector('b')).toBeNull();
  });

  it('only renders manual message and history tabs', async () => {
    const el = await setup();
    const tabLabels = Array.from(el.querySelectorAll<HTMLButtonElement>('[role="tab"]')).map(
      (button) => button.textContent?.trim(),
    );

    expect(tabLabels).toEqual(['Message', 'History']);
    expect(el.textContent).not.toContain('AI assistance');
    expect(el.querySelector<HTMLButtonElement>('[aria-label="Run AI triage"]')).toBeNull();
  });

  it('falls back to the message tab for old ai-assistance links', async () => {
    const el = await setup(QUESTION, [PREVIOUS_QUESTION], 'ai-assistance');

    expect(el.querySelector('#message-tab')?.classList).toContain('question-detail__tab--active');
    expect(el.querySelector('#history-tab')?.classList).not.toContain(
      'question-detail__tab--active',
    );
  });

  it('sends a sanitized answer for submitted questions', async () => {
    const el = await setup();
    const editor = el.querySelector<HTMLElement>('.reply-editor')!;
    editor.innerHTML = '<p onclick="bad()">Answer <script>bad()</script><strong>body</strong></p>';
    editor.dispatchEvent(new Event('input'));
    fixture.detectChanges();
    Array.from(el.querySelectorAll<HTMLButtonElement>('button'))
      .find((button) => button.textContent?.includes('Send response'))!
      .click();
    await fixture.whenStable();

    expect(service.answerCalls).toEqual([['q1', '<p>Answer <strong>body</strong></p>']]);
  });

  it('requires confirmation before marking out of scope', async () => {
    const el = await setup();
    const reason = el.querySelector<HTMLTextAreaElement>('#question-out-of-scope-reason')!;
    reason.value = ' Exhibition ';
    reason.dispatchEvent(new Event('input'));
    fixture.detectChanges();
    const button = () =>
      Array.from(el.querySelectorAll<HTMLButtonElement>('button')).find((b) =>
        b.textContent?.includes('out of scope'),
      )!;

    button().click();
    fixture.detectChanges();
    expect(service.outOfScopeCalls).toEqual([]);
    expect(el.textContent).toContain('standard out-of-scope e-mail');

    button().click();
    await fixture.whenStable();
    expect(service.outOfScopeCalls).toEqual([['q1', 'Exhibition']]);
  });

  it('closes answered questions after confirmation', async () => {
    const el = await setup({ ...QUESTION, status: 'ANSWERED', answerBody: 'Done' });
    const button = () =>
      Array.from(el.querySelectorAll<HTMLButtonElement>('button')).find(
        (b) =>
          b.textContent?.includes('Close question') || b.textContent?.includes('Confirm close'),
      )!;

    button().click();
    fixture.detectChanges();
    expect(service.closeCalls).toEqual([]);
    expect(el.textContent).toContain('No e-mail will be sent');

    button().click();
    await fixture.whenStable();
    expect(service.closeCalls).toEqual(['q1']);
  });

  it('lists previous messages from the same requester email in the history tab', async () => {
    const el = await setup();

    el.querySelector<HTMLButtonElement>('#history-tab')!.click();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(service.listCalls.at(-1)).toMatchObject({
      requesterEmail: 'ana@example.org',
      page: 0,
      size: 100,
    });
    expect(el.textContent).toContain('Previous messages');
    expect(el.textContent).toContain('Previous collections visit');
    expect(el.textContent).toContain('Did the museum previously allow visits to the archives?');
    expect(el.textContent).not.toContain('Different requester');
    expect(
      el.querySelector<HTMLAnchorElement>('a[href="/p/museum-questions/q-previous"]'),
    ).not.toBeNull();
  });

  it('keeps later related messages visible when viewing an older history item', async () => {
    const el = await setup(PREVIOUS_QUESTION, [QUESTION, OTHER_REQUESTER_QUESTION]);

    el.querySelector<HTMLButtonElement>('#history-tab')!.click();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(el.textContent).toContain('Visit question');
    expect(el.querySelector<HTMLAnchorElement>('a[href="/p/museum-questions/q1"]')).not.toBeNull();
  });
});
