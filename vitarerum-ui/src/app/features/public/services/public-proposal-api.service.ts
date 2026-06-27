import { HttpClient } from '@angular/common/http';
import { inject, Injectable, InjectionToken } from '@angular/core';
import { API_BASE_URL } from '@core/config/app-config.model';
import { buildApiUrl } from '@core/http/api-url.util';
import { Observable } from 'rxjs';

import {
  PublicConfirmationResult,
  PublicProposalSubmission,
  PublicSubmissionReceipt,
} from '../models/public-proposal.model';

export interface PublicProposalApi {
  /** Opens an unverified submission and triggers the confirmation e-mail. */
  submit(submission: PublicProposalSubmission): Observable<PublicSubmissionReceipt>;
  /** Finalises a submission from the single-use token in the e-mailed link. */
  confirm(token: string): Observable<PublicConfirmationResult>;
}

export const PUBLIC_PROPOSAL_API_SERVICE = new InjectionToken<PublicProposalApi>(
  'PUBLIC_PROPOSAL_API_SERVICE',
);

/**
 * Talks to the PUBLIC proposal endpoints. These requests are intentionally
 * unauthenticated — the authInterceptor passes them through untouched because
 * there is no session token. No cookies/credentials are attached.
 */
@Injectable()
export class PublicProposalApiService implements PublicProposalApi {
  private readonly http = inject(HttpClient);
  private readonly apiBaseUrl = inject(API_BASE_URL);

  submit(submission: PublicProposalSubmission): Observable<PublicSubmissionReceipt> {
    return this.http.post<PublicSubmissionReceipt>(this.url('/public/proposals'), submission);
  }

  confirm(token: string): Observable<PublicConfirmationResult> {
    return this.http.post<PublicConfirmationResult>(this.url('/public/proposals/confirm'), {
      token,
    });
  }

  private url(path: string): string {
    return buildApiUrl(this.apiBaseUrl, path);
  }
}
