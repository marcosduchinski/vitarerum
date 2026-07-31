import { inject, Injectable } from '@angular/core';
import { IDENTITY_SERVICE } from '@core/auth/identity.service';
import { PermissionPrincipal } from '@core/auth/models/permission.model';
import { Observable, of } from 'rxjs';

import {
  MarkAllNotificationsReadResponse,
  Notification,
  NotificationListQuery,
  NotificationPage,
  UnreadCountResponse,
} from '../models/notification.model';
import { NotificationApi } from '../services/notification-api.service';

const ACTOR: PermissionPrincipal = {
  permissionId: 'perm-collections',
  user: {
    id: 'user-collections',
    name: 'Collections desk',
    email: 'collections@example.com',
  },
  group: 'COLLECTIONS_MANAGEMENT',
};

@Injectable()
export class NotificationApiServiceMock implements NotificationApi {
  private readonly identity = inject(IDENTITY_SERVICE);
  private readonly items = new Map<string, Notification[]>();

  listNotifications(query: NotificationListQuery = {}): Observable<NotificationPage> {
    const page = query.page ?? 0;
    const size = query.size ?? 20;
    const source = this.activeItems().filter((item) => !query.unreadOnly || item.readAt === null);
    const content = source.slice(page * size, page * size + size);
    return of({
      content,
      page,
      size,
      totalElements: source.length,
      totalPages: source.length === 0 ? 0 : Math.ceil(source.length / size),
    });
  }

  getUnreadCount(): Observable<UnreadCountResponse> {
    return of({ count: this.activeItems().filter((item) => item.readAt === null).length });
  }

  markRead(notificationId: string): Observable<Notification> {
    const updated = this.activeItems().map((item) =>
      item.id === notificationId ? { ...item, readAt: item.readAt ?? new Date().toISOString() } : item,
    );
    this.items.set(this.permissionId(), updated);
    return of(updated.find((item) => item.id === notificationId) ?? this.seed()[0]);
  }

  markAllRead(): Observable<MarkAllNotificationsReadResponse> {
    const now = new Date().toISOString();
    const current = this.activeItems();
    const count = current.filter((item) => item.readAt === null).length;
    this.items.set(
      this.permissionId(),
      current.map((item) => ({ ...item, readAt: item.readAt ?? now })),
    );
    return of({ count });
  }

  clearAll(): Observable<MarkAllNotificationsReadResponse> {
    const current = this.activeItems();
    this.items.set(this.permissionId(), []);
    return of({ count: current.length });
  }

  private activeItems(): Notification[] {
    const permissionId = this.permissionId();
    if (!this.items.has(permissionId)) {
      this.items.set(permissionId, this.seed());
    }
    return this.items.get(permissionId) ?? [];
  }

  private permissionId(): string {
    return this.identity.getPermissionId() ?? 'mock-permission';
  }

  private seed(): Notification[] {
    return [
      {
        id: 'notif-submitted-1',
        kind: 'PROPOSAL_SUBMITTED',
        relatedResourceType: 'PROPOSAL',
        relatedResourceId: 'proposal-submitted-zoology',
        relatedResourceLabel: 'PROP-2026-003',
        triggeredBy: ACTOR,
        note: null,
        createdAt: new Date(Date.now() - 1000 * 60 * 8).toISOString(),
        readAt: null,
      },
      {
        id: 'notif-forwarded-1',
        kind: 'PROPOSAL_FORWARDED',
        relatedResourceType: 'PROPOSAL',
        relatedResourceId: 'proposal-pending-zoology',
        relatedResourceLabel: 'PROP-2026-001',
        triggeredBy: ACTOR,
        note: 'Please review the object list before the end of the week.',
        createdAt: new Date(Date.now() - 1000 * 60 * 18).toISOString(),
        readAt: null,
      },
      {
        id: 'notif-assigned-1',
        kind: 'PROPOSAL_ASSIGNED',
        relatedResourceType: 'PROPOSAL',
        relatedResourceId: 'proposal-pending-botany',
        relatedResourceLabel: 'PROP-2026-002',
        triggeredBy: ACTOR,
        note: null,
        createdAt: new Date(Date.now() - 1000 * 60 * 60 * 4).toISOString(),
        readAt: new Date(Date.now() - 1000 * 60 * 20).toISOString(),
      },
    ];
  }
}
