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

  it('groups public enquiries with all, new, and my enquiries submenus for staff', () => {
    activeSession.set(sessionForGroup('COLLECTIONS_MANAGEMENT'));
    const fixture = TestBed.createComponent(AppMenuComponent);
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.textContent).toContain('Use of Collections');

    buttonByText(compiled, 'Public Inquiries').click();
    fixture.detectChanges();

    expect(linkByText(compiled, 'All Enquiries').getAttribute('href')).toBe('/p/museum-questions');
    expect(linkByText(compiled, 'New Inquiries').getAttribute('href')).toBe(
      '/p/museum-questions/new',
    );
    expect(linkByText(compiled, 'My Enquiries').getAttribute('href')).toBe(
      '/p/museum-questions/my',
    );
  });

  it('does not show public inquiries for direction', () => {
    activeSession.set(sessionForGroup('DIRECTION'));
    const fixture = TestBed.createComponent(AppMenuComponent);
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.textContent).toContain('Use of Collections');
    expect(compiled.textContent).not.toContain('Public Inquiries');
    expect(compiled.textContent).not.toContain('All Enquiries');
    expect(compiled.textContent).not.toContain('New Inquiries');
    expect(compiled.textContent).not.toContain('My Enquiries');
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

  it('groups prompts, the knowledge base, scientific return, and watchers under AI for staff', () => {
    activeSession.set(sessionForGroup('CURATORIAL'));
    const fixture = TestBed.createComponent(AppMenuComponent);
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    const promptsLink = linkByText(compiled, 'Prompts');
    expect(compiled.textContent).toContain('AI');
    expect(promptsLink.getAttribute('href')).toBe('/p/ai/prompts');
    expect(promptsLink.querySelector('.pi-file-edit')).not.toBeNull();
    const knowledgeLink = linkByText(compiled, 'Knowledge Base');
    expect(knowledgeLink.getAttribute('href')).toBe('/p/ai/knowledge-base');
    expect(knowledgeLink.querySelector('.pi-book')).not.toBeNull();
    expect(linkByText(compiled, 'Scientific return').getAttribute('href')).toBe(
      '/p/collections/projects/scientific-return',
    );
    expect(linkByText(compiled, 'Watchers').getAttribute('href')).toBe(
      '/p/collections/projects/watchers',
    );

    buttonByText(compiled, 'Projects').click();
    fixture.detectChanges();
    const projectsMenu = buttonByText(compiled, 'Projects').getAttribute('aria-controls');
    const projectsSubmenu = projectsMenu ? compiled.querySelector(`#${projectsMenu}`) : null;
    expect(projectsSubmenu?.textContent).not.toContain('Scientific return');
    expect(projectsSubmenu?.textContent).not.toContain('Watchers');
    expect(compiled.textContent).not.toContain('Scientific Return Test');
  });

  it('shows reference masks only to system administrators', () => {
    activeSession.set(sessionForGroup('SYS_ADMIN'));
    const fixture = TestBed.createComponent(AppMenuComponent);
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    const referenceMasksLink = linkByText(compiled, 'Reference masks');
    expect(referenceMasksLink.getAttribute('href')).toBe('/p/admin/reference-number-policies');

    activeSession.set(sessionForGroup('COLLECTIONS_MANAGEMENT'));
    fixture.detectChanges();

    expect(compiled.textContent).not.toContain('Reference masks');
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
