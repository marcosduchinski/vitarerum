import { Injectable } from '@angular/core';
import { delay, Observable, of } from 'rxjs';

import {
  PublicConfirmationResult,
  PublicProposalSubmission,
  PublicSubmissionReceipt,
} from '../models/public-proposal.model';
import { PublicProposalApi } from '../services/public-proposal-api.service';

/**
 * In-memory stand-in for the public proposal endpoints so the page works with
 * `use-mock-api: true`. It mimics the honeypot accept-and-drop behaviour and
 * the double opt-in shape, but performs NO real protection — that is the
 * server's job in production.
 */
@Injectable()
export class PublicProposalApiServiceMock implements PublicProposalApi {
  submit(submission: PublicProposalSubmission): Observable<PublicSubmissionReceipt> {
    // Honeypot tripped: pretend success so a bot learns nothing.
    // (The real server does the same, server-side.)
    return of<PublicSubmissionReceipt>({
      status: 'PENDING_CONFIRMATION',
      email: submission.citizenEmail,
    }).pipe(delay(400));
  }

  confirm(token: string): Observable<PublicConfirmationResult> {
    const status = token?.trim() ? 'CONFIRMED' : 'INVALID';
    return of<PublicConfirmationResult>({
      status,
      referenceNumber: status === 'CONFIRMED' ? 'VRP-PUBLIC-DEMO-0001' : undefined,
    }).pipe(delay(400));
  }
}
