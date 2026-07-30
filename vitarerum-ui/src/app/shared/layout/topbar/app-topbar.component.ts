import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { Notification } from '@features/notifications/models/notification.model';
import { NotificationsFacade } from '@features/notifications/state/notifications.facade';
import { MenuItem } from 'primeng/api';
import { Menu } from 'primeng/menu';
import { Popover } from 'primeng/popover';

import { IDENTITY_SERVICE } from '@core/auth/identity.service';
import { GroupName } from '@core/auth/models/group-name.enum';
import { LayoutService } from '@layout/layout.service';
import { LogoMarkComponent } from '@shared/components/logo-mark/logo-mark.component';

const GROUP_LABELS: Record<GroupName, string> = {
  EXTERNAL: 'External researcher',
  COLLECTIONS_MANAGEMENT: 'Collections management',
  CURATORIAL: 'Curatorial',
  DIRECTION: 'Direction',
  SYS_ADMIN: 'Administrator',
};

@Component({
  selector: 'app-topbar',
  standalone: true,
  imports: [RouterLink, Menu, Popover, LogoMarkComponent],
  templateUrl: './app-topbar.component.html',
  styleUrl: './app-topbar.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AppTopbarComponent {
  protected readonly layoutService = inject(LayoutService);
  private readonly identity = inject(IDENTITY_SERVICE);
  private readonly router = inject(Router);
  protected readonly notifications = inject(NotificationsFacade);

  protected readonly session = this.identity.session;
  protected readonly isStaff = this.identity.isStaff;
  protected readonly currentGroup = computed(() => this.session()?.group ?? null);
  protected readonly institutionName = computed(() => this.session()?.institution?.name ?? '');

  protected readonly availableGroups = computed(() =>
    (this.session()?.availableGroups ?? []).map((g) => ({ value: g, label: GROUP_LABELS[g] })),
  );

  protected readonly showSwitcher = computed(() => this.availableGroups().length > 1);

  protected readonly userMenuItems = computed<MenuItem[]>(() => {
    const name = this.session()?.user.displayName;
    return [
      ...(name ? [{ label: name, disabled: true }] : []),
      { separator: true },
      {
        label: 'Change password',
        icon: 'pi pi-key',
        command: () => void this.router.navigateByUrl('/p/account/password'),
      },
      {
        label: 'Sign out',
        icon: 'pi pi-sign-out',
        command: () => this.signOut(),
      },
    ];
  });

  protected onGroupChange(event: Event): void {
    const value = (event.target as HTMLSelectElement).value as GroupName;
    this.identity.setGroup(value);
    void this.router.navigateByUrl('/p/dashboard');
  }

  protected async openNotifications(event: Event, popover: Popover): Promise<void> {
    popover.toggle(event);
    await this.notifications.loadRecent();
  }

  protected async openNotification(notification: Notification, popover: Popover): Promise<void> {
    await this.notifications.markRead(notification);
    popover.hide();
    const link = this.notificationLink(notification);
    if (link !== null) {
      await this.router.navigateByUrl(link);
    }
  }

  protected async markAllNotificationsRead(): Promise<void> {
    await this.notifications.markAllRead();
  }

  protected notificationText(notification: Notification): string {
    const label = notification.relatedResourceLabel ?? notification.relatedResourceId ?? 'Proposal';
    const actor = notification.triggeredBy?.user.name ?? 'A staff member';
    switch (notification.kind) {
      case 'PROPOSAL_SUBMITTED':
        return `${actor} submitted ${label}.`;
      case 'PROPOSAL_FORWARDED':
        return `${actor} forwarded ${label} to you.`;
      case 'PROPOSAL_DOCUMENTS_SUBMITTED':
        return `${actor} submitted documents for ${label}.`;
      case 'PROPOSAL_CORRECTIONS_SUBMITTED':
        return `Corrections were submitted for ${label}.`;
      case 'PROPOSAL_ASSIGNED':
        return `${actor} assigned ${label} to you.`;
    }
  }

  protected notificationMeta(notification: Notification): string {
    return new Intl.DateTimeFormat(undefined, {
      day: '2-digit',
      month: 'short',
      hour: '2-digit',
      minute: '2-digit',
    }).format(new Date(notification.createdAt));
  }

  protected notificationLink(notification: Notification): string | null {
    if (notification.relatedResourceType === 'PROPOSAL' && notification.relatedResourceId) {
      return `/p/collections/proposals/${notification.relatedResourceId}`;
    }
    return null;
  }

  private signOut(): void {
    this.identity.signOut();
    void this.router.navigateByUrl('/login');
  }
}
