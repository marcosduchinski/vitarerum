import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of } from 'rxjs';

import {
  MuseumQuestionTriage,
  SearchTermDraft,
  TriageVerdict,
  UseCategoryClassification,
  UseCategoryClassificationAudit,
  UseCategoryClassificationAuditList,
  UseCategoryHumanOutcome,
  UseCategoryValue,
} from '../../models/museum-question-triage.model';
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

const NOT_REQUESTED_USE_CATEGORY_CLASSIFICATION: UseCategoryClassification = {
  status: 'NOT_REQUESTED',
  outcome: null,
  quality: null,
  classifierKind: null,
  classifierModel: null,
  classifierVersion: null,
  assignedCategories: [],
  categoryScores: [],
  classifiedAt: null,
  error: null,
};

const OUT_OF_SCOPE_TRIAGE: MuseumQuestionTriage = {
  id: 't1',
  questionId: 'q1',
  verdict: 'OUT_OF_SCOPE',
  effectiveVerdict: 'OUT_OF_SCOPE',
  staffOverrideVerdict: null,
  isVisitRelated: false,
  mentionedObjects: [],
  objectMatches: [],
  suggestedReply: 'This falls outside the collection-use scope.',
  searchStrategy: null,
  modelName: 'llama3.1:8b',
  createdAt: '2026-07-05T12:00:00Z',
  useCategoryClassification: NOT_REQUESTED_USE_CATEGORY_CLASSIFICATION,
};

const IN_SCOPE_TRIAGE: MuseumQuestionTriage = {
  id: 't2',
  questionId: 'q1',
  verdict: 'IN_SCOPE',
  effectiveVerdict: 'IN_SCOPE',
  staffOverrideVerdict: null,
  isVisitRelated: true,
  mentionedObjects: [
    { english: 'Allende meteorite', portuguese: 'Meteorito Allende', origin: 'AI' },
    { english: 'Ghost object', portuguese: 'Objeto fantasma', origin: 'AI' },
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
      languagesSearched: ['pt', 'en'],
    },
    {
      english: 'Ghost object',
      portuguese: 'Objeto fantasma',
      hits: [],
      languagesSearched: ['pt', 'en'],
    },
  ],
  suggestedReply: null,
  searchStrategy: 'Correspondência aproximada por similaridade textual (não é busca exata).',
  modelName: 'llama3.1:8b',
  createdAt: '2026-07-05T12:00:00Z',
  useCategoryClassification: NOT_REQUESTED_USE_CATEGORY_CLASSIFICATION,
};

const PENDING_USE_CATEGORY_CLASSIFICATION: UseCategoryClassification = {
  status: 'PENDING',
  outcome: null,
  quality: null,
  classifierKind: 'LLM',
  classifierModel: 'llama3.1:8b',
  classifierVersion: 'llm-use-category-v1',
  assignedCategories: [],
  categoryScores: [],
  classifiedAt: null,
  error: null,
};

const COMPLETED_USE_CATEGORY_CLASSIFICATION: UseCategoryClassification = {
  status: 'COMPLETED',
  outcome: 'CATEGORIZED',
  quality: 'FULL',
  classifierKind: 'LLM',
  classifierModel: 'llama3.1:8b',
  classifierVersion: 'llm-use-category-v1',
  assignedCategories: [{ category: 'RESEARCH_PROJECTS', confidence: 0.91, source: 'LLM' }],
  categoryScores: [{ category: 'RESEARCH_PROJECTS', confidence: 0.91, source: 'LLM' }],
  classifiedAt: '2026-07-05T12:01:00Z',
  error: null,
};

const CASCADE_USE_CATEGORY_CLASSIFICATION: UseCategoryClassificationAudit = {
  id: 'classification-cascade',
  triageId: 't2',
  runNumber: 2,
  supersededAt: null,
  metadata: {},
  createdAt: '2026-07-05T12:02:00Z',
  status: 'COMPLETED',
  outcome: 'CATEGORIZED',
  quality: 'FULL',
  classifierKind: 'CASCADE',
  classifierModel: 'cascade-use-category',
  classifierVersion: 'cascade-use-category-v1',
  assignedCategories: [
    { category: 'RESEARCH_PROJECTS', confidence: 0.94, source: 'EMBEDDING' },
    { category: 'ANSWERING_ENQUIRIES', confidence: 0.82, source: 'LLM' },
  ],
  categoryScores: [
    { category: 'RESEARCH_PROJECTS', confidence: 0.94, source: 'EMBEDDING' },
    { category: 'ANSWERING_ENQUIRIES', confidence: 0.82, source: 'LLM' },
  ],
  classifiedAt: '2026-07-05T12:02:00Z',
  error: null,
};

const UNCLEAR_USE_CATEGORY_CLASSIFICATION: UseCategoryClassification = {
  status: 'COMPLETED',
  outcome: 'UNCLEAR',
  quality: 'FULL',
  classifierKind: 'LLM',
  classifierModel: 'llama3.1:8b',
  classifierVersion: 'llm-use-category-v1',
  assignedCategories: [],
  categoryScores: [],
  classifiedAt: '2026-07-05T12:01:00Z',
  error: null,
};

const FAILED_USE_CATEGORY_CLASSIFICATION: UseCategoryClassification = {
  status: 'FAILED',
  outcome: null,
  quality: null,
  classifierKind: 'LLM',
  classifierModel: 'llama3.1:8b',
  classifierVersion: 'llm-use-category-v1',
  assignedCategories: [],
  categoryScores: [],
  classifiedAt: '2026-07-05T12:01:00Z',
  error: 'model unavailable',
};

class ServiceStub {
  question = QUESTION;
  historyQuestions: MuseumQuestion[] = [PREVIOUS_QUESTION, OTHER_REQUESTER_QUESTION];
  triage: MuseumQuestionTriage | null = null;
  nextTriage: MuseumQuestionTriage | null = null;
  readonly listCalls: MuseumQuestionListQuery[] = [];
  readonly answerCalls: [string, string][] = [];
  readonly outOfScopeCalls: [string, string | null][] = [];
  readonly closeCalls: string[] = [];
  readonly getTriageCalls: string[] = [];
  readonly triageCalls: string[] = [];
  readonly overrideVerdictCalls: [string, TriageVerdict][] = [];
  readonly syncSearchTermsCalls: [string, readonly SearchTermDraft[]][] = [];
  readonly syncUseCategoriesCalls: [
    string,
    readonly UseCategoryValue[],
    UseCategoryHumanOutcome,
  ][] = [];
  audit: UseCategoryClassificationAuditList | null = null;

  getTriage(questionId: string) {
    this.getTriageCalls.push(questionId);
    return of(this.triage);
  }

  listTriageClassifications() {
    return of(this.audit);
  }

  runTriage(questionId: string) {
    this.triageCalls.push(questionId);
    this.triage = this.nextTriage;
    this.audit = this.audit ?? null;
    return of(this.triage!);
  }

  overrideTriageVerdict(questionId: string, verdict: TriageVerdict) {
    this.overrideVerdictCalls.push([questionId, verdict]);
    this.triage = {
      ...this.triage!,
      staffOverrideVerdict: verdict,
      effectiveVerdict: verdict,
      searchStrategy: verdict === 'IN_SCOPE' ? 'Correspondência aproximada.' : null,
      suggestedReply:
        verdict === 'OUT_OF_SCOPE' && !this.triage!.suggestedReply
          ? 'Drafted out-of-scope reply.'
          : this.triage!.suggestedReply,
    };
    return of(this.triage);
  }

  syncTriageSearchTerms(questionId: string, terms: readonly SearchTermDraft[]) {
    this.syncSearchTermsCalls.push([questionId, terms]);
    this.triage = {
      ...this.triage!,
      mentionedObjects: terms.map((term) => ({ ...term, origin: 'STAFF' })),
      objectMatches: terms.map((term) => ({ ...term, hits: [], languagesSearched: ['pt'] })),
    };
    return of(this.triage);
  }

  syncTriageUseCategories(
    questionId: string,
    categories: readonly UseCategoryValue[],
    humanOutcome: UseCategoryHumanOutcome,
  ) {
    this.syncUseCategoriesCalls.push([questionId, categories, humanOutcome]);
    const scores = categories.map((category) => ({
      category,
      confidence: 1,
      source: 'LLM' as const,
    }));
    const classification: UseCategoryClassificationAudit = {
      id: 'classification-staff',
      triageId: this.triage!.id,
      runNumber: 3,
      supersededAt: null,
      metadata: { staff_reviewed: true },
      createdAt: '2026-07-05T12:03:00Z',
      status: 'COMPLETED',
      outcome: humanOutcome,
      quality: 'FULL',
      classifierKind: 'CASCADE',
      classifierModel: null,
      classifierVersion: 'staff-reviewed-v1',
      assignedCategories: scores,
      categoryScores: scores,
      classifiedAt: '2026-07-05T12:03:00Z',
      error: null,
    };
    this.audit = { triageId: this.triage!.id, classifications: [classification] };
    return of(this.audit);
  }

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

  it('lists previous messages from the same requester email in the history tab', async () => {
    const el = await setup();
    const tabLabels = Array.from(el.querySelectorAll<HTMLButtonElement>('[role="tab"]')).map(
      (button) => button.textContent?.trim(),
    );

    expect(tabLabels).toEqual(['Message', 'History', 'AI assistance']);

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
    expect(
      el.querySelector<HTMLAnchorElement>('a[href="/p/museum-questions/q1"]'),
    ).not.toBeNull();
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

  it('does not allow AI triage for closed questions', async () => {
    const el = await setup({ ...QUESTION, status: 'CLOSED', closedAt: '2026-07-05T12:00:00Z' });

    expect(el.querySelector<HTMLButtonElement>('[aria-label="Run AI triage"]')).toBeNull();

    el.querySelector<HTMLButtonElement>('#ai-assistance-tab')!.click();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(el.textContent).toContain('AI triage unavailable');
    expect(
      Array.from(el.querySelectorAll<HTMLButtonElement>('button')).some((button) =>
        button.textContent?.includes('Run AI triage'),
      ),
    ).toBe(false);

    fixture.componentInstance['triggerTriage'](service.question);
    await fixture.whenStable();
    expect(service.triageCalls).toEqual([]);
  });

  it('explains what the AI assistance tab checks', async () => {
    const el = await setup();

    el.querySelector<HTMLButtonElement>('#ai-assistance-tab')!.click();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const explainer = el.querySelector('.search-explainer')!;

    expect(explainer.querySelector('summary')?.textContent).toContain('How AI assistance works');
    expect(explainer.textContent).toContain('Scope');
    expect(explainer.textContent).toContain('Objects');
    expect(explainer.textContent).toContain('Use categories');
    expect(explainer.textContent).toContain('AI triage estimates whether the request is in scope');
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

  it('adds the suggested out-of-scope reply to the message reply editor', async () => {
    const el = await setup();
    service.nextTriage = OUT_OF_SCOPE_TRIAGE;

    el.querySelector<HTMLButtonElement>('[aria-label="Run AI triage"]')!.click();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    Array.from(el.querySelectorAll<HTMLButtonElement>('button'))
      .find((button) => button.textContent?.includes('Use in reply'))!
      .click();
    await new Promise((resolve) => setTimeout(resolve));
    fixture.detectChanges();

    expect(
      el.querySelector('#message-tab')?.classList.contains('question-detail__tab--active'),
    ).toBe(true);
    const editor = el.querySelector<HTMLElement>('.reply-editor')!;
    expect(editor.textContent).toContain('This falls outside the collection-use scope.');
  });

  it('renders object matches, including a not-found case, for an in-scope triage result', async () => {
    const el = await setup();
    service.nextTriage = IN_SCOPE_TRIAGE;

    el.querySelector<HTMLButtonElement>('[aria-label="Run AI triage"]')!.click();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(el.textContent).toContain('In scope');
    expect(el.textContent).toContain('Objects searched');
    expect(el.textContent).toContain('Catalogue results');
    expect(el.textContent).toContain('Meteorito Allende');
    expect(el.textContent).toContain('Allende meteorite');
    expect(el.textContent).toContain('Meteorites');
    expect(el.textContent).toContain('Objeto fantasma');
    expect(el.textContent).toContain('Not found in catalogue.');
    expect(el.querySelector('mark')?.textContent).toBe('Allende');
  });

  it('selects and unselects catalogue hits from the result list', async () => {
    const el = await setup();
    service.nextTriage = IN_SCOPE_TRIAGE;

    el.querySelector<HTMLButtonElement>('[aria-label="Run AI triage"]')!.click();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const checkbox = el.querySelector<HTMLInputElement>('.triage-hit-row input[type="checkbox"]')!;
    expect(checkbox.checked).toBe(false);
    expect(el.textContent).toContain('0 selected');

    checkbox.click();
    fixture.detectChanges();
    expect(checkbox.checked).toBe(true);
    expect(el.textContent).toContain('1 selected');

    checkbox.click();
    fixture.detectChanges();
    expect(checkbox.checked).toBe(false);
    expect(el.textContent).toContain('0 selected');
  });

  it('opens catalogue result details in a modal and toggles selection there', async () => {
    const el = await setup();
    service.nextTriage = IN_SCOPE_TRIAGE;

    el.querySelector<HTMLButtonElement>('[aria-label="Run AI triage"]')!.click();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    Array.from(el.querySelectorAll<HTMLButtonElement>('button'))
      .find((button) => button.textContent?.includes('Details'))!
      .click();
    fixture.detectChanges();

    const dialog = el.querySelector<HTMLElement>('[role="dialog"]')!;
    expect(dialog).not.toBeNull();
    expect(dialog.textContent).toContain('Catalogue result');
    expect(dialog.textContent).toContain('Meteorito Allende');
    expect(dialog.textContent).toContain('Allende meteorite');
    expect(dialog.textContent).toContain('rows.xlsx');
    expect(dialog.textContent).toContain('Not selected');

    Array.from(dialog.querySelectorAll<HTMLButtonElement>('button'))
      .find((button) => button.textContent?.includes('Select result'))!
      .click();
    fixture.detectChanges();

    expect(el.textContent).toContain('1 selected');
    expect(el.querySelector<HTMLElement>('[role="dialog"]')?.textContent).toContain('Selected');
  });

  it('adds selected catalogue hits to the message reply editor', async () => {
    const el = await setup();
    service.nextTriage = IN_SCOPE_TRIAGE;

    el.querySelector<HTMLButtonElement>('[aria-label="Run AI triage"]')!.click();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    el.querySelector<HTMLInputElement>('.triage-hit-row input[type="checkbox"]')!.click();
    fixture.detectChanges();

    Array.from(el.querySelectorAll<HTMLButtonElement>('button'))
      .find((button) => button.textContent?.includes('Add to reply'))!
      .click();
    await new Promise((resolve) => setTimeout(resolve));
    fixture.detectChanges();

    expect(
      el.querySelector('#message-tab')?.classList.contains('question-detail__tab--active'),
    ).toBe(true);
    const editor = el.querySelector<HTMLElement>('.reply-editor')!;
    expect(editor.textContent).toContain('Catalogue references found for your request:');
    expect(editor.textContent).toContain('Meteorito Allende (Allende meteorite)');
    expect(editor.textContent).toContain('Meteorites - rows.xlsx');
    expect(editor.textContent).toContain('Allende meteorite');
  });

  it('escapes unsafe markup in an object match highlight, keeping only <mark>', async () => {
    const el = await setup();
    service.nextTriage = {
      ...IN_SCOPE_TRIAGE,
      mentionedObjects: [
        { english: 'Allende meteorite', portuguese: 'Meteorito Allende', origin: 'AI' },
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
          languagesSearched: ['pt'],
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

  it('renders the catalogue search strategy line when in scope', async () => {
    const el = await setup();
    service.nextTriage = IN_SCOPE_TRIAGE;

    el.querySelector<HTMLButtonElement>('[aria-label="Run AI triage"]')!.click();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(el.textContent).toContain('Correspondência aproximada por similaridade textual');
    expect(el.textContent).toContain('pt + en');
  });

  it('renders pending use-category classification without re-running triage', async () => {
    const el = await setup();
    service.nextTriage = {
      ...IN_SCOPE_TRIAGE,
      useCategoryClassification: PENDING_USE_CATEGORY_CLASSIFICATION,
    };

    el.querySelector<HTMLButtonElement>('[aria-label="Run AI triage"]')!.click();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(el.textContent).toContain('Categorias de uso detectadas');
    expect(el.textContent).toContain('Processando classificação de categorias');
    expect(service.triageCalls).toEqual(['q1']);

    Array.from(el.querySelectorAll<HTMLButtonElement>('button'))
      .find((button) => button.textContent?.includes('Atualizar'))!
      .click();
    fixture.detectChanges();
    await fixture.whenStable();

    expect(service.triageCalls).toEqual(['q1']);
    expect(service.getTriageCalls.length).toBeGreaterThan(1);
  });

  it('renders completed use-category chips', async () => {
    const el = await setup();
    service.nextTriage = {
      ...IN_SCOPE_TRIAGE,
      useCategoryClassification: COMPLETED_USE_CATEGORY_CLASSIFICATION,
    };

    el.querySelector<HTMLButtonElement>('[aria-label="Run AI triage"]')!.click();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(el.textContent).toContain('Research projects');
    expect(el.textContent).toContain('91%');
    expect(el.textContent).toContain('Catalogue search');
    expect(el.textContent).toContain('LLM');
  });

  it('uses the operational classification returned by the triage response', async () => {
    const el = await setup();
    service.nextTriage = {
      ...IN_SCOPE_TRIAGE,
      useCategoryClassification: COMPLETED_USE_CATEGORY_CLASSIFICATION,
    };
    service.audit = {
      triageId: 't2',
      classifications: [
        {
          id: 'classification-llm',
          triageId: 't2',
          runNumber: 1,
          supersededAt: '2026-07-05T12:02:00Z',
          metadata: {},
          createdAt: '2026-07-05T12:01:00Z',
          ...COMPLETED_USE_CATEGORY_CLASSIFICATION,
        },
        CASCADE_USE_CATEGORY_CLASSIFICATION,
      ],
    };

    el.querySelector<HTMLButtonElement>('[aria-label="Run AI triage"]')!.click();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(el.textContent).toContain('Operational: LLM');
    expect(el.textContent).toContain('91%');
    expect(el.textContent).not.toContain('94%');
    expect(el.textContent).toContain('2 category(s)');
  });

  it('saves staff-corrected use categories', async () => {
    const el = await setup();
    service.nextTriage = {
      ...IN_SCOPE_TRIAGE,
      useCategoryOperationalClassifier: 'CASCADE_CALIBRATED',
      useCategoryClassification: CASCADE_USE_CATEGORY_CLASSIFICATION,
    };
    service.audit = {
      triageId: 't2',
      classifications: [CASCADE_USE_CATEGORY_CLASSIFICATION],
    };

    el.querySelector<HTMLButtonElement>('[aria-label="Run AI triage"]')!.click();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const publishingLabel = Array.from(el.querySelectorAll<HTMLLabelElement>('label')).find(
      (label) => label.textContent?.includes('Publishing images'),
    )!;
    publishingLabel.querySelector<HTMLInputElement>('input')!.click();
    fixture.detectChanges();

    Array.from(el.querySelectorAll<HTMLButtonElement>('button'))
      .find((button) => button.textContent?.includes('Save categories'))!
      .click();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(service.syncUseCategoriesCalls).toEqual([
      ['q1', ['ANSWERING_ENQUIRIES', 'PUBLISHING_IMAGES', 'RESEARCH_PROJECTS'], 'CATEGORIZED'],
    ]);
  });

  it('renders unclear use-category classification', async () => {
    const el = await setup();
    service.nextTriage = {
      ...IN_SCOPE_TRIAGE,
      useCategoryClassification: UNCLEAR_USE_CATEGORY_CLASSIFICATION,
    };

    el.querySelector<HTMLButtonElement>('[aria-label="Run AI triage"]')!.click();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(el.textContent).toContain('Sem categoria suficientemente clara');
  });

  it('renders failed use-category classification without blocking triage actions', async () => {
    const el = await setup();
    service.nextTriage = {
      ...IN_SCOPE_TRIAGE,
      useCategoryClassification: FAILED_USE_CATEGORY_CLASSIFICATION,
    };

    el.querySelector<HTMLButtonElement>('[aria-label="Run AI triage"]')!.click();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(el.textContent).toContain('Classificação indisponível');
    expect(el.textContent).toContain('model unavailable');
    expect(
      Array.from(el.querySelectorAll<HTMLButtonElement>('button')).some((button) =>
        button.textContent?.includes('Marcar como fora de escopo'),
      ),
    ).toBe(true);
  });

  it('contests the verdict and flips the displayed view without re-running triage', async () => {
    const el = await setup();
    service.nextTriage = IN_SCOPE_TRIAGE;

    el.querySelector<HTMLButtonElement>('[aria-label="Run AI triage"]')!.click();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const contestButton = () =>
      Array.from(el.querySelectorAll<HTMLButtonElement>('button')).find((b) =>
        b.textContent?.includes('Marcar como'),
      )!;

    expect(contestButton().textContent).toContain('Marcar como fora de escopo');
    contestButton().click();
    fixture.detectChanges();
    expect(service.overrideVerdictCalls).toEqual([]);
    expect(el.textContent).toContain('Confirm mark out of scope');

    Array.from(el.querySelectorAll<HTMLButtonElement>('button'))
      .find((b) => b.textContent?.trim() === 'Confirm mark out of scope')!
      .click();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(service.overrideVerdictCalls).toEqual([['q1', 'OUT_OF_SCOPE']]);
    expect(el.textContent).toContain('Drafted out-of-scope reply.');
  });

  it('edits and submits search terms, replacing only what changed', async () => {
    const el = await setup();
    service.nextTriage = IN_SCOPE_TRIAGE;

    el.querySelector<HTMLButtonElement>('[aria-label="Run AI triage"]')!.click();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const portugueseInputs = () =>
      Array.from(el.querySelectorAll<HTMLInputElement>('.triage-terms-editor__row input')).filter(
        (input, index) => index % 2 === 0,
      );

    portugueseInputs()[0].value = 'Vulpes vulpes';
    portugueseInputs()[0].dispatchEvent(new Event('input'));
    fixture.detectChanges();

    Array.from(el.querySelectorAll<HTMLButtonElement>('button'))
      .find((b) => b.textContent?.trim() === 'Search')!
      .click();
    await fixture.whenStable();

    expect(service.syncSearchTermsCalls.length).toBe(1);
    const [questionId, terms] = service.syncSearchTermsCalls[0];
    expect(questionId).toBe('q1');
    expect(terms[0].portuguese).toBe('Vulpes vulpes');
    expect(terms.length).toBe(2);
  });

  it('shows the search term limit and disables adding terms at the cap', async () => {
    const el = await setup();
    service.nextTriage = IN_SCOPE_TRIAGE;

    el.querySelector<HTMLButtonElement>('[aria-label="Run AI triage"]')!.click();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const addTermButton = () =>
      Array.from(el.querySelectorAll<HTMLButtonElement>('button')).find((b) =>
        b.textContent?.includes('Add term'),
      )!;

    expect(el.textContent).toContain('2/10 terms');
    expect(addTermButton().disabled).toBe(false);

    for (let i = 0; i < 8; i += 1) {
      addTermButton().click();
      fixture.detectChanges();
    }

    expect(el.textContent).toContain('10/10 terms');
    expect(addTermButton().disabled).toBe(true);
  });
});
