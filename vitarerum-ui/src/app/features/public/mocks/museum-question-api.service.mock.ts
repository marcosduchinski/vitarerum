import { Injectable } from '@angular/core';
import { delay, Observable, of } from 'rxjs';

import { MuseumQuestionReceipt, MuseumQuestionSubmission } from '../models/museum-question.model';
import { MuseumQuestionApi } from '../services/museum-question-api.service';

/**
 * In-memory stand-in for the public museum-questions endpoint so the page
 * works with `use-mock-api: true`. Performs NO real protection — that is the
 * server's job in production.
 */
@Injectable()
export class MuseumQuestionApiServiceMock implements MuseumQuestionApi {
  submit(submission: MuseumQuestionSubmission): Observable<MuseumQuestionReceipt> {
    return of<MuseumQuestionReceipt>({
      status: 'RECEIVED',
      email: submission.requesterEmail,
    }).pipe(delay(400));
  }
}
