import { HttpClient, HttpParams } from '@angular/common/http';
import { inject, Injectable, InjectionToken } from '@angular/core';
import { API_BASE_URL } from '@core/config/app-config.model';
import { buildApiUrl } from '@core/http/api-url.util';
import { Observable } from 'rxjs';

import {
  AnswerMuseumQuestionRequest,
  ForwardMuseumQuestionRequest,
  MarkOutOfScopeRequest,
  MuseumQuestion,
  MuseumQuestionAttachment,
  MuseumQuestionListQuery,
  MuseumQuestionPage,
} from '../models/museum-question.model';

export interface MuseumQuestionManagementApi {
  list(query: MuseumQuestionListQuery): Observable<MuseumQuestionPage>;
  get(questionId: string): Observable<MuseumQuestion>;
  answer(questionId: string, body: AnswerMuseumQuestionRequest): Observable<MuseumQuestion>;
  forward(questionId: string, body: ForwardMuseumQuestionRequest): Observable<MuseumQuestion>;
  markOutOfScope(questionId: string, body: MarkOutOfScopeRequest): Observable<MuseumQuestion>;
  close(questionId: string): Observable<MuseumQuestion>;
  getAttachment(questionId: string, attachment: MuseumQuestionAttachment): Observable<Blob>;
}

export const MUSEUM_QUESTION_MANAGEMENT_SERVICE = new InjectionToken<MuseumQuestionManagementApi>(
  'MUSEUM_QUESTION_MANAGEMENT_SERVICE',
);

@Injectable()
export class MuseumQuestionManagementService implements MuseumQuestionManagementApi {
  private readonly http = inject(HttpClient);
  private readonly apiBaseUrl = inject(API_BASE_URL);

  list(query: MuseumQuestionListQuery): Observable<MuseumQuestionPage> {
    let params = new HttpParams().set('page', query.page).set('size', query.size);
    if (query.status) params = params.set('status', query.status);
    if (query.requesterEmail) params = params.set('requesterEmail', query.requesterEmail);
    if (query.assignedTo) params = params.set('assignedTo', query.assignedTo);
    if (query.unassignedOnly) params = params.set('unassignedOnly', true);
    return this.http.get<MuseumQuestionPage>(this.url('/museum-questions'), { params });
  }

  get(questionId: string): Observable<MuseumQuestion> {
    return this.http.get<MuseumQuestion>(this.url(`/museum-questions/${questionId}`));
  }

  answer(questionId: string, body: AnswerMuseumQuestionRequest): Observable<MuseumQuestion> {
    return this.http.post<MuseumQuestion>(this.url(`/museum-questions/${questionId}/answer`), body);
  }

  forward(questionId: string, body: ForwardMuseumQuestionRequest): Observable<MuseumQuestion> {
    return this.http.post<MuseumQuestion>(
      this.url(`/museum-questions/${questionId}/forward`),
      body,
    );
  }

  markOutOfScope(questionId: string, body: MarkOutOfScopeRequest): Observable<MuseumQuestion> {
    return this.http.post<MuseumQuestion>(
      this.url(`/museum-questions/${questionId}/mark-out-of-scope`),
      body,
    );
  }

  close(questionId: string): Observable<MuseumQuestion> {
    return this.http.patch<MuseumQuestion>(this.url(`/museum-questions/${questionId}/close`), {});
  }

  getAttachment(questionId: string, attachment: MuseumQuestionAttachment): Observable<Blob> {
    return this.http.get(
      this.url(
        `/museum-questions/${encodeURIComponent(questionId)}/attachments/${encodeURIComponent(
          attachment.id,
        )}`,
      ),
      { responseType: 'blob' },
    );
  }

  private url(path: string): string {
    return buildApiUrl(this.apiBaseUrl, path);
  }
}
