import { HttpClient, HttpParams } from '@angular/common/http';
import { inject, Injectable, InjectionToken } from '@angular/core';
import { API_BASE_URL } from '@core/config/app-config.model';
import { buildApiUrl } from '@core/http/api-url.util';
import { Observable } from 'rxjs';

import {
  AnswerMuseumQuestionRequest,
  MarkOutOfScopeRequest,
  MuseumQuestion,
  MuseumQuestionListQuery,
  MuseumQuestionPage,
} from '../models/museum-question.model';

export interface MuseumQuestionManagementApi {
  list(query: MuseumQuestionListQuery): Observable<MuseumQuestionPage>;
  get(questionId: string): Observable<MuseumQuestion>;
  answer(questionId: string, body: AnswerMuseumQuestionRequest): Observable<MuseumQuestion>;
  markOutOfScope(questionId: string, body: MarkOutOfScopeRequest): Observable<MuseumQuestion>;
  close(questionId: string): Observable<MuseumQuestion>;
}

export const MUSEUM_QUESTION_MANAGEMENT_SERVICE =
  new InjectionToken<MuseumQuestionManagementApi>('MUSEUM_QUESTION_MANAGEMENT_SERVICE');

@Injectable()
export class MuseumQuestionManagementService implements MuseumQuestionManagementApi {
  private readonly http = inject(HttpClient);
  private readonly apiBaseUrl = inject(API_BASE_URL);

  list(query: MuseumQuestionListQuery): Observable<MuseumQuestionPage> {
    let params = new HttpParams().set('page', query.page).set('size', query.size);
    if (query.status) params = params.set('status', query.status);
    return this.http.get<MuseumQuestionPage>(this.url('/museum-questions'), { params });
  }

  get(questionId: string): Observable<MuseumQuestion> {
    return this.http.get<MuseumQuestion>(this.url(`/museum-questions/${questionId}`));
  }

  answer(questionId: string, body: AnswerMuseumQuestionRequest): Observable<MuseumQuestion> {
    return this.http.post<MuseumQuestion>(this.url(`/museum-questions/${questionId}/answer`), body);
  }

  markOutOfScope(
    questionId: string,
    body: MarkOutOfScopeRequest,
  ): Observable<MuseumQuestion> {
    return this.http.post<MuseumQuestion>(
      this.url(`/museum-questions/${questionId}/mark-out-of-scope`),
      body,
    );
  }

  close(questionId: string): Observable<MuseumQuestion> {
    return this.http.patch<MuseumQuestion>(this.url(`/museum-questions/${questionId}/close`), {});
  }

  private url(path: string): string {
    return buildApiUrl(this.apiBaseUrl, path);
  }
}
