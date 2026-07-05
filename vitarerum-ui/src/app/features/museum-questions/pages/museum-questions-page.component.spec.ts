import { ComponentFixture, TestBed } from '@angular/core/testing';
import { of } from 'rxjs';

import {
  MuseumQuestion,
  MuseumQuestionListQuery,
  MuseumQuestionPage,
} from '../models/museum-question.model';
import { MUSEUM_QUESTION_MANAGEMENT_SERVICE } from '../services/museum-question-management.service';
import { MuseumQuestionsPageComponent } from './museum-questions-page.component';

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

class ServiceStub {
  question = QUESTION;
  readonly listCalls: MuseumQuestionListQuery[] = [];
  readonly answerCalls: [string, string][] = [];
  readonly outOfScopeCalls: [string, string | null][] = [];
  readonly closeCalls: string[] = [];

  list(query: MuseumQuestionListQuery) {
    this.listCalls.push(query);
    return of<MuseumQuestionPage>({
      content: [this.question],
      page: query.page,
      size: query.size,
      totalElements: 1,
      totalPages: 1,
    });
  }

  get() {
    return of(this.question);
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

describe('MuseumQuestionsPageComponent', () => {
  let fixture: ComponentFixture<MuseumQuestionsPageComponent>;
  let service: ServiceStub;

  async function setup(question: MuseumQuestion = QUESTION): Promise<HTMLElement> {
    service = new ServiceStub();
    service.question = question;
    await TestBed.configureTestingModule({
      imports: [MuseumQuestionsPageComponent],
      providers: [{ provide: MUSEUM_QUESTION_MANAGEMENT_SERVICE, useValue: service }],
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
    expect(service.listCalls[0]).toMatchObject({ status: 'SUBMITTED', page: 0, size: 20 });
  });

  it('loads detail and keeps citizen content as text', async () => {
    const el = await setup();
    el.querySelector<HTMLButtonElement>('.question-row')!.click();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(el.textContent).toContain('<b>Please do not render as HTML</b>');
    expect(el.querySelector('b')).toBeNull();
  });

  it('sends an answer for submitted questions', async () => {
    const el = await setup();
    await selectFirst(el, fixture);
    const textarea = el.querySelector<HTMLTextAreaElement>('textarea')!;
    textarea.value = '  Answer body  ';
    textarea.dispatchEvent(new Event('input'));
    fixture.detectChanges();
    Array.from(el.querySelectorAll<HTMLButtonElement>('button'))
      .find((button) => button.textContent?.includes('Send answer'))!
      .click();
    await fixture.whenStable();

    expect(service.answerCalls).toEqual([['q1', 'Answer body']]);
  });

  it('requires confirmation before marking out of scope', async () => {
    const el = await setup();
    await selectFirst(el, fixture);
    const reason = Array.from(el.querySelectorAll<HTMLTextAreaElement>('textarea'))[1];
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
    await selectFirst(el, fixture);
    const button = () =>
      Array.from(el.querySelectorAll<HTMLButtonElement>('button')).find((b) =>
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
});

async function selectFirst(
  el: HTMLElement,
  fixture: ComponentFixture<MuseumQuestionsPageComponent>,
): Promise<void> {
  el.querySelector<HTMLButtonElement>('.question-row')!.click();
  fixture.detectChanges();
  await fixture.whenStable();
  fixture.detectChanges();
}
