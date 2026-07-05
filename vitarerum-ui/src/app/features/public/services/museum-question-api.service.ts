import { HttpClient } from '@angular/common/http';
import { inject, Injectable, InjectionToken } from '@angular/core';
import { API_BASE_URL } from '@core/config/app-config.model';
import { buildApiUrl } from '@core/http/api-url.util';
import { Observable } from 'rxjs';

import { MuseumQuestionReceipt, MuseumQuestionSubmission } from '../models/museum-question.model';

export interface MuseumQuestionApi {
  /** Submits a public question; the server persists it as SUBMITTED. */
  submit(submission: MuseumQuestionSubmission): Observable<MuseumQuestionReceipt>;
}

export const MUSEUM_QUESTION_API_SERVICE = new InjectionToken<MuseumQuestionApi>(
  'MUSEUM_QUESTION_API_SERVICE',
);

/**
 * Talks to the PUBLIC museum-questions endpoint. Intentionally unauthenticated
 * — the authInterceptor passes these requests through untouched because there
 * is no session token. No cookies/credentials are attached.
 */
@Injectable()
export class MuseumQuestionApiService implements MuseumQuestionApi {
  private readonly http = inject(HttpClient);
  private readonly apiBaseUrl = inject(API_BASE_URL);

  submit(submission: MuseumQuestionSubmission): Observable<MuseumQuestionReceipt> {
    return this.http.post<MuseumQuestionReceipt>(this.url('/public/museum-questions'), {
      requesterName: submission.requesterName,
      requesterEmail: submission.requesterEmail,
      subject: submission.subject,
      message: submission.message,
      consent: submission.consent,
      captchaToken: submission.captchaToken,
      website: submission.website ?? '',
    });
  }

  private url(path: string): string {
    return buildApiUrl(this.apiBaseUrl, path);
  }
}
