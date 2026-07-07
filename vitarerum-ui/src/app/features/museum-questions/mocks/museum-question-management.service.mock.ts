import { Injectable } from '@angular/core';
import { delay, Observable, of, throwError } from 'rxjs';

import { MuseumQuestionTriage } from '../models/museum-question-triage.model';
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
    return of(this.triages[questionId] ?? null).pipe(delay(150));
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
          isVisitRelated: false,
          mentionedObjects: [],
          objectMatches: [],
          suggestedReply:
            'Thank you for reaching out. This channel handles questions about using the ' +
            'collection for study or in-situ investigation visits, and your question falls ' +
            'outside that scope. Please contact the appropriate department for exhibitions, ' +
            'loans, events, or education, or rephrase your question if it was actually about ' +
            'the collection.',
          modelName: 'llama3.1:8b (mock)',
          createdAt: NOW,
        }
      : {
          id: `triage-${questionId}-${Date.now()}`,
          questionId,
          verdict: 'IN_SCOPE',
          isVisitRelated: true,
          mentionedObjects: [
            {
              english: 'Zoology reference collection',
              portuguese: 'Coleção de referência de zoologia',
            },
            { english: 'Unknown specimen X', portuguese: 'Espécime desconhecido X' },
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
            },
            {
              english: 'Unknown specimen X',
              portuguese: 'Espécime desconhecido X',
              hits: [],
            },
          ],
          suggestedReply: null,
          modelName: 'llama3.1:8b (mock)',
          createdAt: NOW,
        };
    this.triages[questionId] = triage;
    return of(triage).pipe(delay(400));
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
