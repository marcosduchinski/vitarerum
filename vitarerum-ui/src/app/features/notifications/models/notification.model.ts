import { PermissionPrincipal } from '@core/auth/models/permission.model';
import { Page, PageQuery } from '@shared/models/page.model';

export type NotificationKind = 'PROPOSAL_ASSIGNED' | 'PROPOSAL_FORWARDED';
export type RelatedResourceType = 'PROPOSAL' | 'PROJECT';

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

