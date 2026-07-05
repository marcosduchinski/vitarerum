import { Page } from '@shared/models/page.model';

export type MuseumQuestionStatus = 'SUBMITTED' | 'ANSWERED' | 'OUT_OF_SCOPE' | 'CLOSED';

export interface MuseumQuestion {
  readonly id: string;
  readonly requesterName: string;
  readonly requesterEmail: string;
  readonly subject: string;
  readonly message: string;
  readonly status: MuseumQuestionStatus;
  readonly createdAt: string;
  readonly answeredAt: string | null;
  readonly answeredBy: string | null;
  readonly answerBody: string | null;
  readonly answerSentAt: string | null;
  readonly outOfScopeAt: string | null;
  readonly outOfScopeBy: string | null;
  readonly outOfScopeReason: string | null;
  readonly outOfScopeEmailSentAt: string | null;
  readonly closedAt: string | null;
  readonly closedBy: string | null;
}

export type MuseumQuestionPage = Page<MuseumQuestion>;

export interface MuseumQuestionListQuery {
  readonly status?: MuseumQuestionStatus | '';
  readonly requesterEmail?: string;
  readonly page: number;
  readonly size: number;
}

export interface AnswerMuseumQuestionRequest {
  readonly answerBody: string;
}

export interface MarkOutOfScopeRequest {
  readonly reason: string | null;
}
