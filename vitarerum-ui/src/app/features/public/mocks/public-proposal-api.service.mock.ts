import { Injectable } from '@angular/core';
import { delay, Observable, of } from 'rxjs';

import {
  PublicAmendmentDocument,
  PublicAmendmentSubmitResult,
  PublicAmendmentView,
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
      referenceNumber: status === 'CONFIRMED' ? 'PP-MUHNAC/COL/2026/0042' : undefined,
    }).pipe(delay(400));
  }

  getAmendment(token: string): Observable<PublicAmendmentView> {
    if (!token.trim()) {
      return of({
        referenceNumber: '',
        status: 'INVALID',
        expiresAt: new Date().toISOString(),
        correctionItems: [],
        documents: [],
      }).pipe(delay(400));
    }
    return of<PublicAmendmentView>({
      referenceNumber: 'PP-MUHNAC/COL/2026/0042',
      status: 'PENDING',
      expiresAt: new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString(),
      correctionItems: [
        {
          id: 'corr-1',
          documentType: 'Supporting document',
          reason: 'Please replace this file with a readable copy.',
          status: 'REQUESTED',
          documentId: 'doc-1',
        },
        {
          id: 'corr-2',
          documentType: 'Authorization form',
          reason: 'Please attach the missing authorization form.',
          status: 'REQUESTED',
          documentId: null,
        },
      ],
      documents: [
        {
          id: 'doc-1',
          type: 'Supporting document',
          fileName: 'blurred-scan.pdf',
        },
      ],
    }).pipe(delay(400));
  }

  addAmendmentDocument(
    _token: string,
    documentType: string,
    file: File,
  ): Observable<PublicAmendmentDocument> {
    return of<PublicAmendmentDocument>({
      id: crypto.randomUUID(),
      type: documentType,
      fileName: file.name,
    }).pipe(delay(400));
  }

  deleteAmendmentDocument(): Observable<void> {
    return of(undefined).pipe(delay(200));
  }

  submitAmendment(): Observable<PublicAmendmentSubmitResult> {
    return of({ status: 'SUBMITTED' as const }).pipe(delay(400));
  }
}
