import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { MenuItem } from 'primeng/api';

import { IDENTITY_SERVICE } from '@core/auth/identity.service';
import { IdentityServiceMock } from '@core/auth/identity.service.mock';
import { NotificationApiServiceMock } from '@features/notifications/mocks/notification-api.service.mock';
import { Notification } from '@features/notifications/models/notification.model';
import { NOTIFICATION_API_SERVICE } from '@features/notifications/services/notification-api.service';
import { NotificationsFacade } from '@features/notifications/state/notifications.facade';
import { LayoutService } from '@layout/layout.service';

import { AppTopbarComponent } from './app-topbar.component';

class LayoutServiceStub {
  readonly isDarkTheme = signal(false);
  onMenuToggle(): void {
    void this.isDarkTheme();
  }
  toggleDarkMode(): void {
    this.isDarkTheme.update((value) => !value);
  }
}

describe('AppTopbarComponent role switcher', () => {
  let identity: IdentityServiceMock;

  beforeEach(async () => {
    identity = new IdentityServiceMock();

    await TestBed.configureTestingModule({
      imports: [AppTopbarComponent],
      providers: [
        provideRouter([]),
        { provide: IDENTITY_SERVICE, useValue: identity },
        { provide: NOTIFICATION_API_SERVICE, useClass: NotificationApiServiceMock },
        { provide: LayoutService, useClass: LayoutServiceStub },
      ],
    }).compileComponents();
  });

  it('shows the switcher only for multi-group accounts', async () => {
    await identity.signIn({ email: 'bob@collections.example.com', password: 'vita2026' });
    const fixture = TestBed.createComponent(AppTopbarComponent);
    fixture.detectChanges();

    expect((fixture.nativeElement as HTMLElement).querySelector('#role-switcher')).toBeNull();
  });

  it('switches the active group and permission before navigating to the dashboard', async () => {
    await identity.signIn({ email: 'fran@staff.example.com', password: 'vita2026' });
    const router = TestBed.inject(Router);
    const navigateSpy = vi.spyOn(router, 'navigateByUrl').mockImplementation(async () => {
      expect(identity.session()!.group).toBe('CURATORIAL');
      expect(identity.getPermissionId()).toBe('perm-fran-curatorial');
      return true;
    });

    const fixture = TestBed.createComponent(AppTopbarComponent);
    fixture.detectChanges();

    const select = (fixture.nativeElement as HTMLElement).querySelector<HTMLSelectElement>(
      '#role-switcher',
    );

    expect(select).not.toBeNull();
    expect(select!.options.length).toBe(3);
    expect(identity.session()!.group).toBe('COLLECTIONS_MANAGEMENT');

    select!.value = 'CURATORIAL';
    select!.dispatchEvent(new Event('change'));
    fixture.detectChanges();

    expect(identity.session()!.group).toBe('CURATORIAL');
    expect(identity.getPermissionId()).toBe('perm-fran-curatorial');
    expect(select!.value).toBe('CURATORIAL');
    expect(navigateSpy).toHaveBeenCalledOnce();
    expect(navigateSpy).toHaveBeenCalledWith('/p/dashboard');
  });

  it('exposes a Change password item that navigates to /p/account/password', async () => {
    await identity.signIn({ email: 'bob@collections.example.com', password: 'vita2026' });
    const router = TestBed.inject(Router);
    const navigateSpy = vi.spyOn(router, 'navigateByUrl').mockResolvedValue(true);

    const fixture = TestBed.createComponent(AppTopbarComponent);
    fixture.detectChanges();

    const items = (
      fixture.componentInstance as unknown as { userMenuItems: () => MenuItem[] }
    ).userMenuItems();
    const changePasswordItem = items.find((item) => item.label === 'Change password');
    expect(changePasswordItem).toBeDefined();

    changePasswordItem!.command!({ item: changePasswordItem!, originalEvent: new Event('click') });

    expect(navigateSpy).toHaveBeenCalledWith('/p/account/password');
  });

  it('renders copy for staff notification kinds', async () => {
    await identity.signIn({ email: 'bob@collections.example.com', password: 'vita2026' });
    const fixture = TestBed.createComponent(AppTopbarComponent);
    const component = fixture.componentInstance as unknown as {
      notificationLink: (notification: Notification) => string | null;
      notificationText: (notification: Notification) => string;
    };
    const baseNotification: Omit<Notification, 'kind'> = {
      id: 'notification-1',
      relatedResourceType: 'PROPOSAL',
      relatedResourceId: 'proposal-1',
      relatedResourceLabel: 'VR-2026-001',
      triggeredBy: {
        permissionId: 'perm-curatorial',
        group: 'CURATORIAL',
        user: {
          id: 'user-curatorial',
          name: 'Alice Curator',
          email: 'alice@example.com',
        },
      },
      note: null,
      createdAt: '2026-07-30T12:00:00Z',
      readAt: null,
    };

    expect(component.notificationText({ ...baseNotification, kind: 'PROPOSAL_SUBMITTED' })).toBe(
      'New proposal VR-2026-001 was submitted.',
    );
    expect(
      component.notificationText({
        ...baseNotification,
        kind: 'MUSEUM_QUESTION_SUBMITTED',
        relatedResourceType: 'MUSEUM_QUESTION',
        relatedResourceId: 'question-1',
        relatedResourceLabel: 'Question about a specimen',
      }),
    ).toBe('New public inquiry Question about a specimen was submitted.');
    expect(
      component.notificationText({
        ...baseNotification,
        kind: 'PROPOSAL_DOCUMENTS_SUBMITTED',
      }),
    ).toBe('Alice Curator submitted documents for VR-2026-001.');
    expect(
      component.notificationText({
        ...baseNotification,
        kind: 'PROPOSAL_CORRECTIONS_SUBMITTED',
      }),
    ).toBe('Corrections were submitted for VR-2026-001.');
    expect(
      component.notificationText({
        ...baseNotification,
        kind: 'PROPOSAL_TAKEN_OVER',
      }),
    ).toBe('Alice Curator took over VR-2026-001.');
    expect(
      component.notificationLink({
        ...baseNotification,
        kind: 'PROPOSAL_DOCUMENTS_SUBMITTED',
      }),
    ).toBe('/p/collections/proposals/my-assignments/proposal-1?tab=documents');
    expect(
      component.notificationLink({
        ...baseNotification,
        kind: 'PROPOSAL_CORRECTIONS_SUBMITTED',
      }),
    ).toBe('/p/collections/proposals/my-assignments/proposal-1?tab=documents');
    expect(
      component.notificationLink({
        ...baseNotification,
        kind: 'PROPOSAL_SUBMITTED',
      }),
    ).toBe('/p/collections/proposals/proposal-1');
    expect(
      component.notificationLink({
        ...baseNotification,
        kind: 'MUSEUM_QUESTION_SUBMITTED',
        relatedResourceType: 'MUSEUM_QUESTION',
        relatedResourceId: 'question-1',
      }),
    ).toBe('/p/museum-questions/question-1');
  });

  it('clears all visible notifications from the popover state', async () => {
    await identity.signIn({ email: 'bob@collections.example.com', password: 'vita2026' });
    const facade = TestBed.inject(NotificationsFacade);
    const fixture = TestBed.createComponent(AppTopbarComponent);
    const component = fixture.componentInstance as unknown as {
      clearNotifications: () => Promise<void>;
    };

    await facade.loadRecent();
    expect(facade.recent().length).toBeGreaterThan(0);

    await component.clearNotifications();

    expect(facade.recent()).toEqual([]);
    expect(facade.unreadCount()).toBe(0);
  });
});
