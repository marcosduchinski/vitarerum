import { effect, inject, Injectable, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { IDENTITY_SERVICE } from '@core/auth/identity.service';

import { Notification } from '../models/notification.model';
import { NOTIFICATION_API_SERVICE } from '../services/notification-api.service';

@Injectable({ providedIn: 'root' })
export class NotificationsFacade {
  private readonly identity = inject(IDENTITY_SERVICE);
  private readonly api = inject(NOTIFICATION_API_SERVICE);

  private readonly unreadCountState = signal(0);
  private readonly recentState = signal<readonly Notification[]>([]);
  private readonly loadingRecentState = signal(false);
  private lastPermissionId: string | null = null;

  readonly unreadCount = this.unreadCountState.asReadonly();
  readonly recent = this.recentState.asReadonly();
  readonly loadingRecent = this.loadingRecentState.asReadonly();

  constructor() {
    effect((onCleanup) => {
      const permissionId = this.identity.getPermissionId();
      const isStaff = this.identity.isStaff();

      if (!isStaff || permissionId === null) {
        this.reset(null);
        return;
      }

      if (permissionId !== this.lastPermissionId) {
        this.reset(permissionId);
        void this.refreshUnreadCount();
      }

      const timer = window.setInterval(() => void this.refreshUnreadCount(), 45_000);
      onCleanup(() => window.clearInterval(timer));
    });
  }

  async refreshUnreadCount(): Promise<void> {
    if (!this.identity.isStaff()) return;
    const response = await firstValueFrom(this.api.getUnreadCount());
    this.unreadCountState.set(response.count);
  }

  async loadRecent(): Promise<void> {
    if (!this.identity.isStaff()) return;
    this.loadingRecentState.set(true);
    try {
      const page = await firstValueFrom(this.api.listNotifications({ page: 0, size: 8 }));
      this.recentState.set(page.content);
      await this.refreshUnreadCount();
    } finally {
      this.loadingRecentState.set(false);
    }
  }

  async markRead(notification: Notification): Promise<void> {
    if (notification.readAt === null) {
      const updated = await firstValueFrom(this.api.markRead(notification.id));
      this.recentState.update((items) =>
        items.map((item) => (item.id === updated.id ? updated : item)),
      );
      await this.refreshUnreadCount();
    }
  }

  async markAllRead(): Promise<void> {
    await firstValueFrom(this.api.markAllRead());
    const now = new Date().toISOString();
    this.recentState.update((items) =>
      items.map((item) => ({ ...item, readAt: item.readAt ?? now })),
    );
    this.unreadCountState.set(0);
  }

  async clearAll(): Promise<void> {
    await firstValueFrom(this.api.clearAll());
    this.recentState.set([]);
    this.unreadCountState.set(0);
  }

  private reset(permissionId: string | null): void {
    this.lastPermissionId = permissionId;
    this.unreadCountState.set(0);
    this.recentState.set([]);
    this.loadingRecentState.set(false);
  }
}
