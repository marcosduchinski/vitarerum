import { PermissionPrincipal } from '@core/auth/models/permission.model';
import { Page, PageQuery } from '@shared/models/page.model';

export type NotificationKind =
  | 'PROPOSAL_SUBMITTED'
  | 'PROPOSAL_ASSIGNED'
  | 'PROPOSAL_FORWARDED'
  | 'PROPOSAL_TAKEN_OVER'
  | 'PROPOSAL_DOCUMENTS_SUBMITTED'
  | 'PROPOSAL_CORRECTIONS_SUBMITTED'
  | 'MUSEUM_QUESTION_SUBMITTED'
  | 'MUSEUM_QUESTION_FORWARDED'
  | 'MUSEUM_QUESTION_RESPONSE_OVERDUE'
  | 'SCIENTIFIC_RETURN_CANDIDATES_FOUND';
export type RelatedResourceType = 'PROPOSAL' | 'PROJECT' | 'MUSEUM_QUESTION';

export interface Notification {
  readonly id: string;
  readonly kind: NotificationKind;
  readonly relatedResourceType: RelatedResourceType | null;
  readonly relatedResourceId: string | null;
  readonly relatedResourceLabel: string | null;
  readonly triggeredBy: PermissionPrincipal | null;
  readonly note: string | null;
  readonly createdAt: string;
  readonly readAt: string | null;
}

export interface NotificationListQuery extends PageQuery {
  readonly unreadOnly?: boolean;
}

export type NotificationPage = Page<Notification>;

export interface UnreadCountResponse {
  readonly count: number;
}

export interface MarkAllNotificationsReadResponse {
  readonly count: number;
}
