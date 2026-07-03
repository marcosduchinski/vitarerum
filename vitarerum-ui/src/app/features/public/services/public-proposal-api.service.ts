import { HttpClient } from '@angular/common/http';
import { inject, Injectable, InjectionToken } from '@angular/core';
import { API_BASE_URL } from '@core/config/app-config.model';
import { buildApiUrl } from '@core/http/api-url.util';
import { Observable } from 'rxjs';

import {
  PublicAmendmentDocument,
  PublicAmendmentSubmitResult,
  PublicAmendmentView,
  PublicConfirmationResult,
  PublicProposalSubmission,
  PublicSubmissionReceipt,
} from '../models/public-proposal.model';

export interface PublicProposalApi {
  /** Opens an unverified submission and triggers the confirmation e-mail. */
  submit(submission: PublicProposalSubmission): Observable<PublicSubmissionReceipt>;
  /** Finalises a submission from the single-use token in the e-mailed link. */
  confirm(token: string): Observable<PublicConfirmationResult>;
  /** Loads the token-scoped document correction screen. */
  getAmendment(token: string): Observable<PublicAmendmentView>;
  /** Uploads a replacement or missing document within the token scope. */
  addAmendmentDocument(
    token: string,
    documentType: string,
    file: File,
  ): Observable<PublicAmendmentDocument>;
  /** Removes a token-scoped document that staff marked for replacement. */
  deleteAmendmentDocument(token: string, documentId: string): Observable<void>;
  /** Marks the amendment complete and burns the single-use token. */
  submitAmendment(token: string): Observable<PublicAmendmentSubmitResult>;
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
    const form = new FormData();
    form.append('citizenName', submission.citizenName);
    form.append('citizenEmail', submission.citizenEmail);
    form.append('subject', submission.subject);
    form.append('body', submission.body);
    form.append('useType', submission.useType);
    form.append('proposedBeginDate', submission.proposedBeginDate);
    form.append('proposedEndDate', submission.proposedEndDate);
    form.append('consent', String(submission.consent));
    form.append('captchaToken', submission.captchaToken);
    form.append('website', submission.website ?? '');
    for (const document of submission.documents) {
      form.append('documents', document, document.name);
    }
    return this.http.post<PublicSubmissionReceipt>(this.url('/public/proposals'), form);
  }

  confirm(token: string): Observable<PublicConfirmationResult> {
    return this.http.post<PublicConfirmationResult>(this.url('/public/proposals/confirm'), {
      token,
    });
  }

  getAmendment(token: string): Observable<PublicAmendmentView> {
    return this.http.get<PublicAmendmentView>(
      this.url(`/public/proposals/amendments/${encodeURIComponent(token)}`),
    );
  }

  addAmendmentDocument(
    token: string,
    documentType: string,
    file: File,
  ): Observable<PublicAmendmentDocument> {
    const form = new FormData();
    form.append('documentType', documentType);
    form.append('file', file, file.name);
    return this.http.post<PublicAmendmentDocument>(
      this.url(`/public/proposals/amendments/${encodeURIComponent(token)}/documents`),
      form,
    );
  }

  deleteAmendmentDocument(token: string, documentId: string): Observable<void> {
    return this.http.delete<void>(
      this.url(
        `/public/proposals/amendments/${encodeURIComponent(token)}/documents/${encodeURIComponent(documentId)}`,
      ),
    );
  }

  submitAmendment(token: string): Observable<PublicAmendmentSubmitResult> {
    return this.http.post<PublicAmendmentSubmitResult>(
      this.url(`/public/proposals/amendments/${encodeURIComponent(token)}/submit`),
      {},
    );
  }

  private url(path: string): string {
    return buildApiUrl(this.apiBaseUrl, path);
  }
}
