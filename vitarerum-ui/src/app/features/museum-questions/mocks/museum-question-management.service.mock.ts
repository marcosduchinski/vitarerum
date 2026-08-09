import { Injectable } from '@angular/core';
import { PermissionPrincipal } from '@core/auth/models/permission.model';
import { delay, Observable, of, throwError } from 'rxjs';

import {
  AnswerMuseumQuestionRequest,
  ForwardMuseumQuestionRequest,
  MarkOutOfScopeRequest,
  MuseumQuestion,
  MuseumQuestionAttachment,
  MuseumQuestionListItem,
  MuseumQuestionListQuery,
  MuseumQuestionPage,
  MuseumQuestionStatus,
} from '../models/museum-question.model';
import { MuseumQuestionManagementApi } from '../services/museum-question-management.service';

const NOW = '2026-07-05T12:00:00Z';

const PRINCIPALS: Record<string, PermissionPrincipal> = {
  'perm-bob': {
    permissionId: 'perm-bob',
    user: { id: 'u-bob', name: 'Bob Santos', email: 'bob@collections.example.com' },
    group: 'COLLECTIONS_MANAGEMENT',
  },
  'perm-carol': {
    permissionId: 'perm-carol',
    user: { id: 'u-carol', name: 'Carol Souza', email: 'carol@curatorial.example.com' },
    group: 'CURATORIAL',
  },
};

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
      responseDueAt: '2026-07-20T10:00:00Z',
      responseOverdueNotifiedAt: null,
      responseOverdue: false,
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
      attachments: [
        {
          id: 'att-1',
          fileName: 'collection-label.png',
          contentType: 'image/png',
          sizeBytes: 1462,
          createdAt: '2026-07-05T10:00:00Z',
        },
      ],
    },
    {
      id: 'q-2',
      requesterName: 'Bruno Lima',
      requesterEmail: 'bruno@example.org',
      subject: 'Exhibition opening hours',
      message: 'Could you tell me the exhibition opening hours?',
      status: 'OUT_OF_SCOPE',
      createdAt: '2026-07-05T11:00:00Z',
      responseDueAt: '2026-07-20T11:00:00Z',
      responseOverdueNotifiedAt: null,
      responseOverdue: false,
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
      assignedTo: null,
      attachments: [],
    },
    {
      id: 'q-3',
      requesterName: 'Ana Souza',
      requesterEmail: 'ana@example.org',
      subject: 'Previous collections visit',
      message: 'Did the museum previously allow visits to the archives?',
      status: 'ANSWERED',
      createdAt: '2026-06-22T09:30:00Z',
      responseDueAt: '2026-07-07T09:30:00Z',
      responseOverdueNotifiedAt: null,
      responseOverdue: false,
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
      assignedTo: PRINCIPALS['perm-carol'],
      attachments: [],
    },
  ];

  list(query: MuseumQuestionListQuery): Observable<MuseumQuestionPage> {
    const filtered = this.filtered(
      query.status,
      query.requesterEmail,
      query.assignedTo,
      query.unassignedOnly ?? false,
    );
    const start = query.page * query.size;
    const content = filtered.slice(start, start + query.size).map((q) => this.toListItem(q));
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

  forward(questionId: string, body: ForwardMuseumQuestionRequest): Observable<MuseumQuestion> {
    const question = this.require(questionId);
    if (question.status !== 'SUBMITTED') return this.invalidTransition();
    const assignedTo = PRINCIPALS[body.targetPermissionId] ?? PRINCIPALS['perm-carol'];
    return of(
      this.replace(questionId, {
        ...question,
        assignedTo,
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

  getAttachment(questionId: string, attachment: MuseumQuestionAttachment): Observable<Blob> {
    this.require(questionId);
    const pngPixel = Uint8Array.from([
      0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0x00, 0x00, 0x00, 0x0d, 0x49, 0x48, 0x44,
      0x52, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01, 0x08, 0x06, 0x00, 0x00, 0x00, 0x1f,
      0x15, 0xc4, 0x89, 0x00, 0x00, 0x00, 0x0a, 0x49, 0x44, 0x41, 0x54, 0x78, 0x9c, 0x63, 0xf8,
      0xcf, 0xc0, 0x00, 0x00, 0x03, 0x01, 0x01, 0x00, 0xc9, 0xfe, 0x92, 0xef, 0x00, 0x00, 0x00,
      0x00, 0x49, 0x45, 0x4e, 0x44, 0xae, 0x42, 0x60, 0x82,
    ]);
    return of(new Blob([pngPixel], { type: attachment.contentType })).pipe(delay(150));
  }

  private filtered(
    status: MuseumQuestionStatus | '' | undefined,
    requesterEmail: string | undefined,
    assignedTo: string | undefined,
    unassignedOnly: boolean,
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
      if (assignedTo && q.assignedTo?.permissionId !== assignedTo) return false;
      if (unassignedOnly && q.assignedTo !== null) return false;
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

  private toListItem(question: MuseumQuestion): MuseumQuestionListItem {
    return {
      id: question.id,
      requesterName: question.requesterName,
      requesterEmail: question.requesterEmail,
      subject: question.subject,
      message: question.message,
      status: question.status,
      createdAt: question.createdAt,
      responseDueAt: question.responseDueAt,
      responseOverdueNotifiedAt: question.responseOverdueNotifiedAt,
      responseOverdue: question.responseOverdue,
      answeredAt: question.answeredAt,
      answeredBy: question.answeredBy,
      answerBody: question.answerBody,
      answerSentAt: question.answerSentAt,
      outOfScopeAt: question.outOfScopeAt,
      outOfScopeBy: question.outOfScopeBy,
      outOfScopeReason: question.outOfScopeReason,
      outOfScopeEmailSentAt: question.outOfScopeEmailSentAt,
      closedAt: question.closedAt,
      closedBy: question.closedBy,
      assignedTo: question.assignedTo,
      attachmentCount: question.attachments.length,
    };
  }

  private notFound(): Observable<never> {
    return throwError(() => ({ status: 404, error: { message: 'Question not found' } }));
  }

  private invalidTransition(): Observable<never> {
    return throwError(() => ({ status: 409, error: { message: 'Invalid question status' } }));
  }
}
