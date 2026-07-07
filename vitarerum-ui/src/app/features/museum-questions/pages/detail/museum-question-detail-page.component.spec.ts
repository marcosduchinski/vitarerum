import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of } from 'rxjs';

import { MuseumQuestionTriage } from '../../models/museum-question-triage.model';
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

const ANSWERED: MuseumQuestion = {
  ...QUESTION,
  id: 'q2',
  subject: 'Previous visit',
  status: 'ANSWERED',
  answeredAt: '2026-07-04T12:00:00Z',
  answeredBy: 'perm-staff',
  answerBody: 'Previous answer',
  answerSentAt: '2026-07-04T12:00:00Z',
};

const OUT_OF_SCOPE_TRIAGE: MuseumQuestionTriage = {
  id: 't1',
  questionId: 'q1',
  verdict: 'OUT_OF_SCOPE',
  isVisitRelated: false,
  mentionedObjects: [],
  objectMatches: [],
  suggestedReply: 'This falls outside the collection-use scope.',
  modelName: 'llama3.1:8b',
  createdAt: '2026-07-05T12:00:00Z',
};

const IN_SCOPE_TRIAGE: MuseumQuestionTriage = {
  id: 't2',
  questionId: 'q1',
  verdict: 'IN_SCOPE',
  isVisitRelated: true,
  mentionedObjects: [
    { english: 'Allende meteorite', portuguese: 'Meteorito Allende' },
    { english: 'Ghost object', portuguese: 'Objeto fantasma' },
  ],
  objectMatches: [
    {
      english: 'Allende meteorite',
      portuguese: 'Meteorito Allende',
      hits: [
        {
          collectionId: 'c1',
          collectionName: 'Meteorites',
          fileName: 'rows.xlsx',
          highlight: '<b>Allende</b> meteorite',
        },
      ],
    },
    { english: 'Ghost object', portuguese: 'Objeto fantasma', hits: [] },
  ],
  suggestedReply: null,
  modelName: 'llama3.1:8b',
  createdAt: '2026-07-05T12:00:00Z',
};

class ServiceStub {
  question = QUESTION;
  triage: MuseumQuestionTriage | null = null;
  nextTriage: MuseumQuestionTriage | null = null;
  readonly listCalls: MuseumQuestionListQuery[] = [];
  readonly answerCalls: [string, string][] = [];
  readonly outOfScopeCalls: [string, string | null][] = [];
  readonly closeCalls: string[] = [];
  readonly triageCalls: string[] = [];

  getTriage() {
    return of(this.triage);
  }

  runTriage(questionId: string) {
    this.triageCalls.push(questionId);
    this.triage = this.nextTriage;
    return of(this.triage!);
  }

  list(query: MuseumQuestionListQuery) {
    this.listCalls.push(query);
    return of<MuseumQuestionPage>({
      content: [ANSWERED],
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

describe('MuseumQuestionDetailPageComponent', () => {
  let fixture: ComponentFixture<MuseumQuestionDetailPageComponent>;
  let service: ServiceStub;

  async function setup(question: MuseumQuestion = QUESTION): Promise<HTMLElement> {
    service = new ServiceStub();
    service.question = question;
    await TestBed.configureTestingModule({
      imports: [MuseumQuestionDetailPageComponent],
      providers: [
        provideRouter([]),
        { provide: MUSEUM_QUESTION_MANAGEMENT_SERVICE, useValue: service },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(MuseumQuestionDetailPageComponent);
    fixture.componentRef.setInput('id', question.id);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  it('renders message detail and keeps citizen content as text', async () => {
    const el = await setup();
    expect(el.textContent).toContain('Visit question');
    expect(el.textContent).toContain('<b>Please do not render as HTML</b>');
    expect(el.querySelector('b')).toBeNull();
  });

  it('sends an answer for submitted questions', async () => {
    const el = await setup();
    const editor = el.querySelector<HTMLElement>('.reply-editor')!;
    editor.innerHTML = 'Answer body';
    editor.dispatchEvent(new Event('input'));
    fixture.detectChanges();
    Array.from(el.querySelectorAll<HTMLButtonElement>('button'))
      .find((button) => button.textContent?.includes('Send response'))!
      .click();
    await fixture.whenStable();

    expect(service.answerCalls).toEqual([['q1', 'Answer body']]);
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

  it('loads answered history for the requester email', async () => {
    const el = await setup();
    Array.from(el.querySelectorAll<HTMLButtonElement>('[role="tab"]'))
      .find((button) => button.textContent?.includes('Answered for this email'))!
      .click();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(service.listCalls.at(-1)).toMatchObject({
      status: 'ANSWERED',
      requesterEmail: 'ana@example.org',
      page: 0,
      size: 10,
    });
    expect(el.textContent).toContain('Previous visit');
    expect(el.textContent).toContain('Previous answer');
  });

  it('runs AI triage from the message icon and switches to the AI assistance tab', async () => {
    const el = await setup();
    service.nextTriage = OUT_OF_SCOPE_TRIAGE;

    el.querySelector<HTMLButtonElement>('[aria-label="Run AI triage"]')!.click();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(service.triageCalls).toEqual(['q1']);
    expect(
      el.querySelector('#ai-assistance-tab')?.classList.contains('question-detail__tab--active'),
    ).toBe(true);
  });

  it('renders the suggested reply for an out-of-scope triage result', async () => {
    const el = await setup();
    service.nextTriage = OUT_OF_SCOPE_TRIAGE;

    el.querySelector<HTMLButtonElement>('[aria-label="Run AI triage"]')!.click();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(el.textContent).toContain('Out of scope');
    expect(el.textContent).toContain('This falls outside the collection-use scope.');
  });

  it('renders object matches, including a not-found case, for an in-scope triage result', async () => {
    const el = await setup();
    service.nextTriage = IN_SCOPE_TRIAGE;

    el.querySelector<HTMLButtonElement>('[aria-label="Run AI triage"]')!.click();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(el.textContent).toContain('In scope');
    expect(el.textContent).toContain('Allende meteorite');
    expect(el.textContent).toContain('Meteorites');
    expect(el.textContent).toContain('Ghost object');
    expect(el.textContent).toContain('Not found in catalogue.');
    expect(el.querySelector('mark')?.textContent).toBe('Allende');
  });

  it('escapes unsafe markup in an object match highlight, keeping only <mark>', async () => {
    const el = await setup();
    service.nextTriage = {
      ...IN_SCOPE_TRIAGE,
      mentionedObjects: [
        { english: 'Allende meteorite', portuguese: 'Meteorito Allende' },
      ],
      objectMatches: [
        {
          english: 'Allende meteorite',
          portuguese: 'Meteorito Allende',
          hits: [
            {
              collectionId: 'c1',
              collectionName: 'Meteorites',
              fileName: 'rows.xlsx',
              highlight: '<img src=x onerror=alert(1)> <b>Allende</b>',
            },
          ],
        },
      ],
    };

    el.querySelector<HTMLButtonElement>('[aria-label="Run AI triage"]')!.click();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(el.querySelector('img')).toBeNull();
    expect(el.textContent).toContain('<img');
    expect(el.querySelector('mark')?.textContent).toBe('Allende');
  });
});
