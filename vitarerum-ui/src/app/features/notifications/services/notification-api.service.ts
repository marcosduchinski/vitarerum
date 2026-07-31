import { HttpClient } from '@angular/common/http';
import { inject, Injectable, InjectionToken } from '@angular/core';
import { API_BASE_URL } from '@core/config/app-config.model';
import { buildApiUrl } from '@core/http/api-url.util';
import { buildHttpParams } from '@core/http/http-params.util';
import { Observable } from 'rxjs';

import {
  MarkAllNotificationsReadResponse,
  Notification,
  NotificationListQuery,
  NotificationPage,
  UnreadCountResponse,
} from '../models/notification.model';

export const NOTIFICATION_API_SERVICE = new InjectionToken<NotificationApi>(
  'NOTIFICATION_API_SERVICE',
);

export interface NotificationApi {
  listNotifications(query?: NotificationListQuery): Observable<NotificationPage>;
  getUnreadCount(): Observable<UnreadCountResponse>;
  markRead(notificationId: string): Observable<Notification>;
  markAllRead(): Observable<MarkAllNotificationsReadResponse>;
  clearAll(): Observable<MarkAllNotificationsReadResponse>;
}

@Injectable()
export class NotificationApiService implements NotificationApi {
  private readonly http = inject(HttpClient);
  private readonly apiBaseUrl = inject(API_BASE_URL);

  listNotifications(query: NotificationListQuery = {}): Observable<NotificationPage> {
    return this.http.get<NotificationPage>(this.url('/notifications'), {
      params: buildHttpParams(query),
    });
  }

  getUnreadCount(): Observable<UnreadCountResponse> {
    return this.http.get<UnreadCountResponse>(this.url('/notifications/unread-count'));
  }

  markRead(notificationId: string): Observable<Notification> {
    return this.http.post<Notification>(this.url(`/notifications/${notificationId}/read`), {});
  }

  markAllRead(): Observable<MarkAllNotificationsReadResponse> {
    return this.http.post<MarkAllNotificationsReadResponse>(
      this.url('/notifications/read-all'),
      {},
    );
  }

  clearAll(): Observable<MarkAllNotificationsReadResponse> {
    return this.http.post<MarkAllNotificationsReadResponse>(
      this.url('/notifications/clear-all'),
      {},
    );
  }

  private url(path: string): string {
    return buildApiUrl(this.apiBaseUrl, path);
  }
}
