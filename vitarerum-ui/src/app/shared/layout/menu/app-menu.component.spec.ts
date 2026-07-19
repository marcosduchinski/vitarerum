import { computed, signal } from '@angular/core';
import { provideRouter } from '@angular/router';
import { TestBed } from '@angular/core/testing';

import { IDENTITY_SERVICE, IdentityService } from '@core/auth/identity.service';
import { GroupName } from '@core/auth/models/group-name.enum';
import { IdentitySession } from '@core/auth/models/identity-session.model';
import { LoginRequest } from '@core/auth/models/login.model';

import { AppMenuComponent } from './app-menu.component';

let activeSession = signal<IdentitySession | null>(null);

class IdentityServiceStub implements IdentityService {
  readonly session = activeSession.asReadonly();
  readonly isAuthenticated = computed(() => activeSession() !== null);
  readonly isStaff = computed(() => {
    const group = activeSession()?.group;
    return group != null && group !== 'EXTERNAL';
  });

  signIn(credentials: LoginRequest): Promise<void> {
    void credentials;
    return Promise.resolve();
  }

  signOut(): void {
    activeSession.set(null);
  }

  getAccessToken(): string | null {
    return activeSession()?.accessToken ?? null;
  }

  getPermissionId(): string | null {
    const session = activeSession();
    return (
      session?.permissions?.find((permission) => permission.group === session.group)
        ?.permissionId ?? null
    );
  }

  setGroup(group: GroupName): void {
    const session = activeSession();
    if (session) activeSession.set({ ...session, group });
  }

  updateAvailableGroups(groups: readonly GroupName[]): void {
    const session = activeSession();
    if (session) activeSession.set({ ...session, availableGroups: [...groups] });
  }

  changePassword(): Promise<void> {
    return Promise.resolve();
  }

  requestPasswordReset(): Promise<void> {
    return Promise.resolve();
  }

  confirmPasswordReset(): Promise<void> {
    return Promise.resolve();
  }
}

describe('AppMenuComponent', () => {
  beforeEach(async () => {
    activeSession = signal<IdentitySession | null>(null);

    await TestBed.configureTestingModule({
      imports: [AppMenuComponent],
      providers: [provideRouter([]), { provide: IDENTITY_SERVICE, useClass: IdentityServiceStub }],
    }).compileComponents();
  });

  it('shows reports for use-of-collections staff', () => {
    activeSession.set(sessionForGroup('COLLECTIONS_MANAGEMENT'));
    const fixture = TestBed.createComponent(AppMenuComponent);
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    buttonByText(compiled, 'Reports').click();
    fixture.detectChanges();

    const visitsLink = linkByText(compiled, 'Visits in situ');
    expect(compiled.textContent).toContain('Reports');
    expect(visitsLink.getAttribute('href')).toBe('/p/collections/reports/visits-in-situ');
  });

  it('shows public inquiries inside use of collections for staff', () => {
    activeSession.set(sessionForGroup('COLLECTIONS_MANAGEMENT'));
    const fixture = TestBed.createComponent(AppMenuComponent);
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    const questionsLink = linkByText(compiled, 'Public Inquiries');
    expect(compiled.textContent).toContain('Use of Collections');
    expect(questionsLink.getAttribute('href')).toBe('/p/museum-questions');
  });

  it('groups object search under objects inside use of collections for staff', () => {
    activeSession.set(sessionForGroup('COLLECTIONS_MANAGEMENT'));
    const fixture = TestBed.createComponent(AppMenuComponent);
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.textContent).toContain('Use of Collections');
    buttonByText(compiled, 'Objects').click();
    fixture.detectChanges();

    const objectSearchLink = linkByText(compiled, 'Object Search');
    expect(objectSearchLink.getAttribute('href')).toBe('/p/objects/search');
  });

  it('shows AI prompts for staff who can generate narratives', () => {
    activeSession.set(sessionForGroup('CURATORIAL'));
    const fixture = TestBed.createComponent(AppMenuComponent);
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    const promptsLink = linkByText(compiled, 'Prompts');
    expect(compiled.textContent).toContain('AI');
    expect(promptsLink.getAttribute('href')).toBe('/p/ai/prompts');
  });

  it('does not show reports for external users', () => {
    activeSession.set(sessionForGroup('EXTERNAL'));
    const fixture = TestBed.createComponent(AppMenuComponent);
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;

    expect(compiled.textContent).not.toContain('Reports');
    expect(compiled.textContent).not.toContain('Visits in situ');
    expect(compiled.textContent).not.toContain('AI');
  });
});

function sessionForGroup(group: GroupName): IdentitySession {
  return {
    accessToken: 'token',
    user: { id: 'user-1', email: 'user@example.test', displayName: 'User' },
    group,
    availableGroups: [group],
    permissions: [{ permissionId: `perm-${group}`, group }],
  };
}

function buttonByText(root: HTMLElement, text: string): HTMLButtonElement {
  const button = Array.from(root.querySelectorAll('button')).find((candidate) =>
    candidate.textContent?.trim().includes(text),
  );
  if (!(button instanceof HTMLButtonElement)) throw new Error(`Button not found: ${text}`);
  return button;
}

function linkByText(root: HTMLElement, text: string): HTMLAnchorElement {
  const link = Array.from(root.querySelectorAll('a')).find((candidate) =>
    candidate.textContent?.trim().includes(text),
  );
  if (!(link instanceof HTMLAnchorElement)) throw new Error(`Link not found: ${text}`);
  return link;
}
