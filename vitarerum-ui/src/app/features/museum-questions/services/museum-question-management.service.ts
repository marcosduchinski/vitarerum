import { HttpClient, HttpErrorResponse, HttpParams } from '@angular/common/http';
import { inject, Injectable, InjectionToken } from '@angular/core';
import { API_BASE_URL } from '@core/config/app-config.model';
import { buildApiUrl } from '@core/http/api-url.util';
import { catchError, map, Observable, of, throwError } from 'rxjs';

import {
  AnswerMuseumQuestionRequest,
  MarkOutOfScopeRequest,
  MuseumQuestion,
  MuseumQuestionListQuery,
  MuseumQuestionPage,
} from '../models/museum-question.model';
import {
  MuseumQuestionTriage,
  SearchTermDraft,
  TriageVerdict,
  UseCategoryClassificationAuditList,
  UseCategoryValue,
} from '../models/museum-question-triage.model';

export interface MuseumQuestionManagementApi {
  list(query: MuseumQuestionListQuery): Observable<MuseumQuestionPage>;
  get(questionId: string): Observable<MuseumQuestion>;
  answer(questionId: string, body: AnswerMuseumQuestionRequest): Observable<MuseumQuestion>;
  markOutOfScope(questionId: string, body: MarkOutOfScopeRequest): Observable<MuseumQuestion>;
  close(questionId: string): Observable<MuseumQuestion>;
  getTriage(questionId: string): Observable<MuseumQuestionTriage | null>;
  listTriageClassifications(
    questionId: string,
  ): Observable<UseCategoryClassificationAuditList | null>;
  runTriage(questionId: string): Observable<MuseumQuestionTriage>;
  overrideTriageVerdict(
    questionId: string,
    verdict: TriageVerdict,
  ): Observable<MuseumQuestionTriage>;
  syncTriageSearchTerms(
    questionId: string,
    terms: readonly SearchTermDraft[],
  ): Observable<MuseumQuestionTriage>;
  syncTriageUseCategories(
    questionId: string,
    categories: readonly UseCategoryValue[],
  ): Observable<UseCategoryClassificationAuditList>;
}

export const MUSEUM_QUESTION_MANAGEMENT_SERVICE = new InjectionToken<MuseumQuestionManagementApi>(
  'MUSEUM_QUESTION_MANAGEMENT_SERVICE',
);

/** Tolerates a backend that hasn't been redeployed with the refinements-plan
 * fields yet (`effectiveVerdict`/`origin`/`languagesSearched`/`searchStrategy`)
 * — backend and frontend are independent deploys. TODO(remove after rollout
 * of the backend refinements is confirmed stable): once that's certain, this
 * mapping and the fallbacks below can go. */
function withFallbacks(raw: MuseumQuestionTriage): MuseumQuestionTriage {
  return {
    ...raw,
    effectiveVerdict: raw.effectiveVerdict ?? raw.verdict,
    searchStrategy: raw.searchStrategy ?? null,
    useCategoryClassification: raw.useCategoryClassification ?? {
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
    },
    mentionedObjects: raw.mentionedObjects.map((obj) => ({
      ...obj,
      origin: obj.origin ?? 'AI',
    })),
    objectMatches: raw.objectMatches.map((match) => ({
      ...match,
      languagesSearched: match.languagesSearched ?? ['pt'],
    })),
  };
}

@Injectable()
export class MuseumQuestionManagementService implements MuseumQuestionManagementApi {
  private readonly http = inject(HttpClient);
  private readonly apiBaseUrl = inject(API_BASE_URL);

  list(query: MuseumQuestionListQuery): Observable<MuseumQuestionPage> {
    let params = new HttpParams().set('page', query.page).set('size', query.size);
    if (query.status) params = params.set('status', query.status);
    if (query.requesterEmail) params = params.set('requesterEmail', query.requesterEmail);
    return this.http.get<MuseumQuestionPage>(this.url('/museum-questions'), { params });
  }

  get(questionId: string): Observable<MuseumQuestion> {
    return this.http.get<MuseumQuestion>(this.url(`/museum-questions/${questionId}`));
  }

  answer(questionId: string, body: AnswerMuseumQuestionRequest): Observable<MuseumQuestion> {
    return this.http.post<MuseumQuestion>(this.url(`/museum-questions/${questionId}/answer`), body);
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

  getTriage(questionId: string): Observable<MuseumQuestionTriage | null> {
    return this.http
      .get<MuseumQuestionTriage>(this.url(`/museum-questions/${questionId}/triage`))
      .pipe(
        map((raw) => withFallbacks(raw)),
        catchError((err: unknown) => {
          if (err instanceof HttpErrorResponse && err.status === 404) return of(null);
          return throwError(() => err);
        }),
      );
  }

  listTriageClassifications(questionId: string): Observable<UseCategoryClassificationAuditList | null> {
    return this.http
      .get<UseCategoryClassificationAuditList>(
        this.url(`/museum-questions/${questionId}/triage/classifications`),
      )
      .pipe(
        catchError((err: unknown) => {
          if (err instanceof HttpErrorResponse && err.status === 404) return of(null);
          return throwError(() => err);
        }),
      );
  }

  runTriage(questionId: string): Observable<MuseumQuestionTriage> {
    return this.http
      .post<MuseumQuestionTriage>(this.url(`/museum-questions/${questionId}/triage`), {})
      .pipe(map((raw) => withFallbacks(raw)));
  }

  overrideTriageVerdict(
    questionId: string,
    verdict: TriageVerdict,
  ): Observable<MuseumQuestionTriage> {
    return this.http
      .patch<MuseumQuestionTriage>(this.url(`/museum-questions/${questionId}/triage/verdict`), {
        verdict,
      })
      .pipe(map((raw) => withFallbacks(raw)));
  }

  syncTriageSearchTerms(
    questionId: string,
    terms: readonly SearchTermDraft[],
  ): Observable<MuseumQuestionTriage> {
    return this.http
      .put<MuseumQuestionTriage>(
        this.url(`/museum-questions/${questionId}/triage/search-terms`),
        { terms },
      )
      .pipe(map((raw) => withFallbacks(raw)));
  }

  syncTriageUseCategories(
    questionId: string,
    categories: readonly UseCategoryValue[],
  ): Observable<UseCategoryClassificationAuditList> {
    return this.http.put<UseCategoryClassificationAuditList>(
      this.url(`/museum-questions/${questionId}/triage/use-categories`),
      { categories },
    );
  }

  private url(path: string): string {
    return buildApiUrl(this.apiBaseUrl, path);
  }
}
