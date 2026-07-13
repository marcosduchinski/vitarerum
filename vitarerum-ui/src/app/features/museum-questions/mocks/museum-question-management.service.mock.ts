import { Injectable } from '@angular/core';
import { delay, Observable, of, throwError } from 'rxjs';

import {
  MentionedObject,
  MuseumQuestionTriage,
  SearchTermDraft,
  TriageVerdict,
  UseCategoryClassification,
  UseCategoryClassificationAudit,
  UseCategoryClassificationAuditList,
  UseCategoryHumanOutcome,
  UseCategoryScore,
  UseCategoryValue,
} from '../models/museum-question-triage.model';
import {
  AnswerMuseumQuestionRequest,
  MarkOutOfScopeRequest,
  MuseumQuestion,
  MuseumQuestionListQuery,
  MuseumQuestionPage,
  MuseumQuestionStatus,
} from '../models/museum-question.model';
import { MuseumQuestionManagementApi } from '../services/museum-question-management.service';

const NOW = '2026-07-05T12:00:00Z';
const SEARCH_STRATEGY_DESCRIPTION =
  'Correspondência aproximada por similaridade textual (não é busca exata).';
const MAX_STAFF_SEARCH_TERMS = 10;

function normalizeTermKey(term: { english: string; portuguese: string }): string {
  return `${term.portuguese.trim().toLowerCase()}::${term.english.trim().toLowerCase()}`;
}

/** Mirrors the backend's `_normalize_object_terms`: trim, drop blank pairs,
 * fall back a missing language to the other, and deduplicate case-
 * insensitively by the (portuguese, english) pair — so the mock behaves the
 * same as the real API for manual QA (blank/duplicate/single-language rows
 * behave identically, not just "happy path" input). */
function normalizeSearchTerms(terms: readonly SearchTermDraft[]): SearchTermDraft[] {
  const seen = new Set<string>();
  const normalized: SearchTermDraft[] = [];
  for (const raw of terms) {
    let english = raw.english.trim();
    let portuguese = raw.portuguese.trim();
    if (!english && !portuguese) continue;
    english = english || portuguese;
    portuguese = portuguese || english;
    const key = `${portuguese.toLowerCase()}::${english.toLowerCase()}`;
    if (seen.has(key)) continue;
    seen.add(key);
    normalized.push({ english, portuguese });
  }
  return normalized;
}

function pendingUseCategoryClassification(): UseCategoryClassification {
  return {
    status: 'PENDING',
    outcome: null,
    quality: null,
    classifierKind: 'LLM',
    classifierModel: 'llama3.1:8b (mock)',
    classifierVersion: 'llm-use-category-v1',
    assignedCategories: [],
    categoryScores: [],
    classifiedAt: null,
    error: null,
  };
}

function completedUseCategoryClassification(): UseCategoryClassification {
  const scores = [
    { category: 'RESEARCH_PROJECTS', confidence: 0.91, source: 'LLM' as const },
    { category: 'ANSWERING_ENQUIRIES', confidence: 0.76, source: 'EMBEDDING' as const },
  ] satisfies UseCategoryScore[];
  return {
    status: 'COMPLETED',
    outcome: 'CATEGORIZED',
    quality: 'FULL',
    classifierKind: 'CASCADE',
    classifierModel: 'cascade (mock)',
    classifierVersion: 'cascade-use-category-v1',
    assignedCategories: scores,
    categoryScores: scores,
    classifiedAt: NOW,
    error: null,
  };
}

function classificationAudit(
  triage: MuseumQuestionTriage,
): UseCategoryClassificationAuditList {
  if (triage.useCategoryClassification.status === 'NOT_REQUESTED') {
    return { triageId: triage.id, classifications: [] };
  }
  const current = triage.useCategoryClassification;
  const classifications: UseCategoryClassificationAudit[] = [
    {
      id: `classification-${triage.id}-current`,
      triageId: triage.id,
      runNumber: 1,
      supersededAt: null,
      metadata: {},
      createdAt: current.classifiedAt ?? NOW,
      ...current,
    },
  ];
  return { triageId: triage.id, classifications };
}

@Injectable()
export class MuseumQuestionManagementServiceMock implements MuseumQuestionManagementApi {
  private questions: MuseumQuestion[] = [
    {
      id: 'q-1',
      requesterName: 'Ana Souza',
      requesterEmail: 'ana@example.org',
      subject: 'Visit to zoology collection',
      message: 'I would like to know how to arrange an in-situ research visit.',
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
    },
    {
      id: 'q-2',
      requesterName: 'Bruno Lima',
      requesterEmail: 'bruno@example.org',
      subject: 'Exhibition opening hours',
      message: 'Could you tell me the exhibition opening hours?',
      status: 'OUT_OF_SCOPE',
      createdAt: '2026-07-05T11:00:00Z',
      answeredAt: null,
      answeredBy: null,
      answerBody: null,
      answerSentAt: null,
      outOfScopeAt: NOW,
      outOfScopeBy: 'perm-staff',
      outOfScopeReason: 'Exhibition question',
      outOfScopeEmailSentAt: NOW,
      closedAt: null,
      closedBy: null,
    },
    {
      id: 'q-3',
      requesterName: 'Ana Souza',
      requesterEmail: 'ana@example.org',
      subject: 'Previous collections visit',
      message: 'Did the museum previously allow visits to the archives?',
      status: 'ANSWERED',
      createdAt: '2026-06-22T09:30:00Z',
      answeredAt: '2026-06-22T15:00:00Z',
      answeredBy: 'perm-staff',
      answerBody: 'Yes. Please coordinate the visit with the collections team.',
      answerSentAt: '2026-06-22T15:00:00Z',
      outOfScopeAt: null,
      outOfScopeBy: null,
      outOfScopeReason: null,
      outOfScopeEmailSentAt: null,
      closedAt: null,
      closedBy: null,
    },
  ];

  list(query: MuseumQuestionListQuery): Observable<MuseumQuestionPage> {
    const filtered = this.filtered(query.status, query.requesterEmail);
    const start = query.page * query.size;
    const content = filtered.slice(start, start + query.size);
    return of({
      content,
      page: query.page,
      size: query.size,
      totalElements: filtered.length,
      totalPages: filtered.length === 0 ? 0 : Math.ceil(filtered.length / query.size),
    }).pipe(delay(250));
  }

  get(questionId: string): Observable<MuseumQuestion> {
    const question = this.questions.find((q) => q.id === questionId);
    return question ? of(question).pipe(delay(150)) : this.notFound();
  }

  answer(questionId: string, body: AnswerMuseumQuestionRequest): Observable<MuseumQuestion> {
    const question = this.require(questionId);
    if (question.status !== 'SUBMITTED') return this.invalidTransition();
    return of(
      this.replace(questionId, {
        ...question,
        status: 'ANSWERED',
        answerBody: body.answerBody.trim(),
        answeredAt: NOW,
        answeredBy: 'perm-staff',
        answerSentAt: NOW,
      }),
    ).pipe(delay(250));
  }

  markOutOfScope(questionId: string, body: MarkOutOfScopeRequest): Observable<MuseumQuestion> {
    const question = this.require(questionId);
    if (question.status !== 'SUBMITTED') return this.invalidTransition();
    return of(
      this.replace(questionId, {
        ...question,
        status: 'OUT_OF_SCOPE',
        outOfScopeAt: NOW,
        outOfScopeBy: 'perm-staff',
        outOfScopeReason: body.reason?.trim() || null,
        outOfScopeEmailSentAt: NOW,
      }),
    ).pipe(delay(250));
  }

  close(questionId: string): Observable<MuseumQuestion> {
    const question = this.require(questionId);
    if (question.status !== 'ANSWERED' && question.status !== 'OUT_OF_SCOPE') {
      return this.invalidTransition();
    }
    return of(
      this.replace(questionId, {
        ...question,
        status: 'CLOSED',
        closedAt: NOW,
        closedBy: 'perm-staff',
      }),
    ).pipe(delay(200));
  }

  private triages: Record<string, MuseumQuestionTriage> = {};

  getTriage(questionId: string): Observable<MuseumQuestionTriage | null> {
    const triage = this.triages[questionId] ?? null;
    if (triage?.useCategoryClassification.status === 'PENDING') {
      const updated = {
        ...triage,
        useCategoryClassification: completedUseCategoryClassification(),
      };
      this.triages[questionId] = updated;
      return of(updated).pipe(delay(150));
    }
    return of(triage).pipe(delay(150));
  }

  listTriageClassifications(questionId: string): Observable<UseCategoryClassificationAuditList | null> {
    const triage = this.triages[questionId] ?? null;
    return of(triage ? classificationAudit(triage) : null).pipe(delay(150));
  }

  syncTriageUseCategories(
    questionId: string,
    categories: readonly UseCategoryValue[],
    humanOutcome: UseCategoryHumanOutcome,
  ): Observable<UseCategoryClassificationAuditList> {
    const triage = this.triages[questionId];
    if (!triage) return this.notFound();
    const scores = [...new Set(categories)].sort().map((category) => ({
      category,
      confidence: 1,
      source: 'LLM' as const,
    }));
    const updated: MuseumQuestionTriage = {
      ...triage,
      useCategoryClassification: {
        status: 'COMPLETED',
        outcome: humanOutcome,
        quality: 'FULL',
        classifierKind: 'CASCADE',
        classifierModel: null,
        classifierVersion: 'staff-reviewed-v1',
        assignedCategories: scores,
        categoryScores: scores,
        classifiedAt: NOW,
        error: null,
      },
    };
    this.triages[questionId] = updated;
    return of(classificationAudit(updated)).pipe(delay(200));
  }

  runTriage(questionId: string): Observable<MuseumQuestionTriage> {
    const question = this.require(questionId);
    const outOfScope = /exhibition|loan|event|educat/i.test(
      `${question.subject} ${question.message}`,
    );
    const triage: MuseumQuestionTriage = outOfScope
      ? {
          id: `triage-${questionId}-${Date.now()}`,
          questionId,
          verdict: 'OUT_OF_SCOPE',
          effectiveVerdict: 'OUT_OF_SCOPE',
          staffOverrideVerdict: null,
          isVisitRelated: false,
          mentionedObjects: [],
          objectMatches: [],
          suggestedReply:
            'Thank you for reaching out. This channel handles questions about using the ' +
            'collection for study or in-situ investigation visits, and your question falls ' +
            'outside that scope. Please contact the appropriate department for exhibitions, ' +
            'loans, events, or education, or rephrase your question if it was actually about ' +
            'the collection.',
          searchStrategy: null,
          modelName: 'llama3.1:8b (mock)',
          createdAt: NOW,
          useCategoryClassification: pendingUseCategoryClassification(),
        }
      : {
          id: `triage-${questionId}-${Date.now()}`,
          questionId,
          verdict: 'IN_SCOPE',
          effectiveVerdict: 'IN_SCOPE',
          staffOverrideVerdict: null,
          isVisitRelated: true,
          mentionedObjects: [
            {
              english: 'Zoology reference collection',
              portuguese: 'Coleção de referência de zoologia',
              origin: 'AI',
            },
            {
              english: 'Unknown specimen X',
              portuguese: 'Espécime desconhecido X',
              origin: 'AI',
            },
          ],
          objectMatches: [
            {
              english: 'Zoology reference collection',
              portuguese: 'Coleção de referência de zoologia',
              hits: [
                {
                  collectionId: 'zoology',
                  collectionName: 'Zoology',
                  fileName: 'zoology-catalogue.xlsx',
                  highlight: 'Zoology <b>reference collection</b>, drawer 12',
                },
              ],
              languagesSearched: ['pt', 'en'],
            },
            {
              english: 'Unknown specimen X',
              portuguese: 'Espécime desconhecido X',
              hits: [],
              languagesSearched: ['pt', 'en'],
            },
          ],
          suggestedReply: null,
          searchStrategy: SEARCH_STRATEGY_DESCRIPTION,
          modelName: 'llama3.1:8b (mock)',
          createdAt: NOW,
          useCategoryClassification: pendingUseCategoryClassification(),
        };
    this.triages[questionId] = triage;
    return of(triage).pipe(delay(400));
  }

  overrideTriageVerdict(
    questionId: string,
    verdict: TriageVerdict,
  ): Observable<MuseumQuestionTriage> {
    const triage = this.triages[questionId];
    if (!triage) return this.notFound();

    const updated: MuseumQuestionTriage = {
      ...triage,
      staffOverrideVerdict: verdict,
      effectiveVerdict: verdict,
      searchStrategy: verdict === 'IN_SCOPE' ? SEARCH_STRATEGY_DESCRIPTION : null,
      suggestedReply:
        verdict === 'OUT_OF_SCOPE' && !triage.suggestedReply
          ? 'Thank you for reaching out. This question falls outside the scope of this channel.'
          : triage.suggestedReply,
    };
    this.triages[questionId] = updated;
    return of(updated).pipe(delay(200));
  }

  syncTriageSearchTerms(
    questionId: string,
    terms: readonly SearchTermDraft[],
  ): Observable<MuseumQuestionTriage> {
    const triage = this.triages[questionId];
    if (!triage) return this.notFound();
    if (triage.effectiveVerdict !== 'IN_SCOPE') {
      return throwError(() => ({
        status: 409,
        error: { error: 'TRIAGE_NOT_IN_SCOPE', message: 'Triage is not in scope.' },
      }));
    }

    const normalizedTerms = normalizeSearchTerms(terms);
    if (normalizedTerms.length > MAX_STAFF_SEARCH_TERMS) {
      return throwError(() => ({
        status: 422,
        error: { error: 'INVALID_SEARCH_TERMS', message: 'Too many search terms.' },
      }));
    }

    const existingTermsByKey = new Map(
      triage.mentionedObjects.map((obj) => [normalizeTermKey(obj), obj]),
    );
    const existingMatchesByKey = new Map(
      triage.objectMatches.map((match) => [normalizeTermKey(match), match]),
    );

    const newTerms: MentionedObject[] = [];
    const newMatches: MuseumQuestionTriage['objectMatches'][number][] = [];
    for (const term of normalizedTerms) {
      const key = normalizeTermKey(term);
      const existingTerm = existingTermsByKey.get(key);
      if (existingTerm) {
        newTerms.push(existingTerm);
        const existingMatch = existingMatchesByKey.get(key);
        if (existingMatch) newMatches.push(existingMatch);
        continue;
      }
      newTerms.push({ english: term.english, portuguese: term.portuguese, origin: 'STAFF' });
      newMatches.push({
        english: term.english,
        portuguese: term.portuguese,
        hits: [],
        languagesSearched: ['pt'],
      });
    }

    const updated: MuseumQuestionTriage = {
      ...triage,
      mentionedObjects: newTerms,
      objectMatches: newMatches,
    };
    this.triages[questionId] = updated;
    return of(updated).pipe(delay(300));
  }

  private filtered(
    status: MuseumQuestionStatus | '' | undefined,
    requesterEmail: string | undefined,
  ): MuseumQuestion[] {
    const ordered = [...this.questions].sort((a, b) => a.createdAt.localeCompare(b.createdAt));
    return ordered.filter((q) => {
      if (status && q.status !== status) return false;
      if (
        requesterEmail &&
        q.requesterEmail.toLowerCase() !== requesterEmail.trim().toLowerCase()
      ) {
        return false;
      }
      return true;
    });
  }

  private require(questionId: string): MuseumQuestion {
    const question = this.questions.find((q) => q.id === questionId);
    if (!question) throw new Error('Question not found');
    return question;
  }

  private replace(questionId: string, question: MuseumQuestion): MuseumQuestion {
    this.questions = this.questions.map((q) => (q.id === questionId ? question : q));
    return question;
  }

  private notFound(): Observable<never> {
    return throwError(() => ({ status: 404, error: { message: 'Question not found' } }));
  }

  private invalidTransition(): Observable<never> {
    return throwError(() => ({ status: 409, error: { message: 'Invalid question status' } }));
  }
}
