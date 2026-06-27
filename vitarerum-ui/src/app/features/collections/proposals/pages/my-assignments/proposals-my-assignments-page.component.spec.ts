import { Router, provideRouter } from '@angular/router';
import { TestBed } from '@angular/core/testing';
import { computed, signal } from '@angular/core';
import { of } from 'rxjs';

import { IDENTITY_SERVICE, IdentityService } from '@core/auth/identity.service';
import { GroupName } from '@core/auth/models/group-name.enum';
import { IdentitySession } from '@core/auth/models/identity-session.model';
import { LoginRequest } from '@core/auth/models/login.model';
import { UserDetail } from '@core/auth/models/user.model';
import { USER_MANAGEMENT_SERVICE } from '@features/admin/services/user-management.service';
import { Page } from '@shared/models/page.model';

import { ProposalListQuery, ProposalSummary } from '../../models/proposal.model';
import { PROPOSAL_API_SERVICE } from '../../services/proposal-api.service';
import { ProposalsMyAssignmentsPageComponent } from './proposals-my-assignments-page.component';

const SESSION: IdentitySession = {
  accessToken: 'token',
  user: {
    id: 'staff-1',
    email: 'bob@example.test',
    displayName: 'Bob Santos',
  },
  group: 'COLLECTIONS_MANAGEMENT',
  availableGroups: ['COLLECTIONS_MANAGEMENT'],
  permissions: [{ permissionId: 'permission-staff', group: 'COLLECTIONS_MANAGEMENT' }],
};

const PROPOSAL: ProposalSummary = {
  id: 'proposal-1',
  referenceNumber: 'VR-2026-001',
  title: 'Photographic history of Rio de Janeiro port, 1890-1930',
  status: 'PENDING',
  type: 'IN_SITU_VISIT',
  requestedBy: {
    permissionId: 'permission-external',
    user: { id: 'user-1', name: 'Alice Ferreira', email: 'alice@example.test' },
    group: 'EXTERNAL',
  },
  assignedTo: {
    permissionId: 'permission-staff',
    user: { id: 'staff-1', name: 'Bob Santos', email: 'bob@example.test' },
    group: 'COLLECTIONS_MANAGEMENT',
  },
  collectionUseProject: {
    id: 'project-1',
    referenceNumber: 'VR-2026-001',
    title: 'Photographic history of Rio de Janeiro port, 1890-1930',
    status: 'CREATED',
  },
  submittedAt: '2026-05-01T10:00:00',
};

const USERS: Page<UserDetail> = {
  content: [
    {
      id: 'user-1',
      name: 'Alice Ferreira',
      email: 'alice@example.test',
      permissions: [
        {
          permissionId: 'permission-external',
          group: { id: 'group-external', name: 'EXTERNAL' },
        },
      ],
    },
    {
      id: 'staff-1',
      name: 'Bob Santos',
      email: 'bob@example.test',
      permissions: [
        {
          permissionId: 'permission-staff',
          group: { id: 'group-collections', name: 'COLLECTIONS_MANAGEMENT' },
        },
      ],
    },
    {
      id: 'staff-2',
      name: 'Carol Lima',
      email: 'carol@example.test',
      permissions: [
        {
          permissionId: 'permission-curatorial',
          group: { id: 'group-curatorial', name: 'CURATORIAL' },
        },
      ],
    },
  ],
  page: 0,
  size: 100,
  totalElements: 3,
  totalPages: 1,
};

class IdentityServiceStub implements IdentityService {
  private readonly sessionState = signal<IdentitySession | null>(SESSION);

  readonly session = this.sessionState.asReadonly();
  readonly isAuthenticated = signal(true).asReadonly();
  readonly isStaff = computed(() => {
    const group = this.session()?.group;
    return group != null && group !== 'EXTERNAL';
  });

  async signIn(credentials: LoginRequest): Promise<void> {
    const { email } = credentials;
    const session = this.sessionState();
    this.sessionState.set(
      session
        ? { ...session, user: { ...session.user, email } }
        : {
            accessToken: 'token',
            user: { id: 'signed-in-user', email, displayName: email },
            group: null,
            availableGroups: [],
          },
    );
  }

  signOut(): void {
    this.sessionState.set(null);
  }

  getAccessToken(): string | null {
    return this.session()?.accessToken ?? null;
  }

  getPermissionId(): string | null {
    const session = this.sessionState();
    if (session === null) return null;
    return session.permissions?.find((p) => p.group === session.group)?.permissionId ?? null;
  }

  setGroup(group: GroupName): void {
    const session = this.sessionState();
    if (session) this.sessionState.set({ ...session, group });
  }

  updateAvailableGroups(groups: readonly GroupName[]): void {
    const session = this.sessionState();
    if (session) this.sessionState.set({ ...session, availableGroups: [...groups] });
  }
}

class ProposalApiServiceStub {
  proposals: ProposalSummary[] = [PROPOSAL];
  readonly queries: ProposalListQuery[] = [];
  readonly forwardCalls: {
    readonly proposalId: string;
    readonly payload: { readonly targetPermissionId: string; readonly note: string };
  }[] = [];

  listProposals(query: ProposalListQuery = {}) {
    this.queries.push(query);
    const size = query.size ?? 20;

    return of<Page<ProposalSummary>>({
      content: this.proposals,
      page: query.page ?? 0,
      size,
      totalElements: 1,
      totalPages: 1,
    });
  }

  forwardProposal(
    proposalId: string,
    payload: { readonly targetPermissionId: string; readonly note: string },
  ) {
    this.forwardCalls.push({ proposalId, payload });
    return of(PROPOSAL);
  }
}

class UserManagementServiceStub {
  listUsers() {
    return of(USERS);
  }
}

describe('ProposalsMyAssignmentsPageComponent', () => {
  let proposalService: ProposalApiServiceStub;
  let router: Router;

  beforeEach(async () => {
    proposalService = new ProposalApiServiceStub();

    await TestBed.configureTestingModule({
      imports: [ProposalsMyAssignmentsPageComponent],
      providers: [
        provideRouter([]),
        { provide: IDENTITY_SERVICE, useClass: IdentityServiceStub },
        { provide: PROPOSAL_API_SERVICE, useValue: proposalService },
        { provide: USER_MANAGEMENT_SERVICE, useClass: UserManagementServiceStub },
      ],
    }).compileComponents();

    router = TestBed.inject(Router);
  });

  it('lists only proposals assigned to the logged user permission', async () => {
    const fixture = TestBed.createComponent(ProposalsMyAssignmentsPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(proposalService.queries.at(-1)).toMatchObject({
      assignedTo: 'permission-staff',
      status: 'PENDING',
      page: 0,
      size: 20,
      search: '',
    });
    expect(proposalService.queries.at(-1)).not.toHaveProperty('requestedBy');
  });

  it('routes proposal rows to the staff detail page', async () => {
    const fixture = TestBed.createComponent(ProposalsMyAssignmentsPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;

    expect(compiled.querySelector('#proposals-search')).not.toBeNull();
    expect(compiled.textContent).toContain('My assignments');
    expect(compiled.textContent).toContain('Reference');
    expect(
      compiled.querySelector('a[href^="/p/collections/proposals/my-assignments/proposal-1"]'),
    ).not.toBeNull();
    expect(compiled.querySelector('[aria-label="More actions for VR-2026-001"]')).not.toBeNull();
  });

  it('keeps a cleared-title assignment link identifiable and accessible', async () => {
    proposalService.proposals = [{ ...PROPOSAL, title: null } as unknown as ProposalSummary];
    const fixture = TestBed.createComponent(ProposalsMyAssignmentsPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    const link = compiled.querySelector<HTMLAnchorElement>(
      'a[href="/p/collections/proposals/my-assignments/proposal-1"]',
    );

    expect(link?.textContent?.trim()).toBe('Untitled proposal');
    expect(compiled.textContent).toContain('VR-2026-001');
  });

  it('shows forward and view details in the row menu', async () => {
    const fixture = TestBed.createComponent(ProposalsMyAssignmentsPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    const actionButton = compiled.querySelector<HTMLButtonElement>(
      '[aria-label="More actions for VR-2026-001"]',
    );

    expect(actionButton).not.toBeNull();

    actionButton!.click();
    fixture.detectChanges();
    await fixture.whenStable();

    expect(document.body.textContent).toContain('Forward');
    expect(document.body.textContent).toContain('Details');
  });

  it('navigates to my-assignments detail on view details', async () => {
    const navigateSpy = vi.spyOn(router, 'navigate').mockResolvedValue(true);

    const fixture = TestBed.createComponent(ProposalsMyAssignmentsPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    const actionButton = compiled.querySelector<HTMLButtonElement>(
      '[aria-label="More actions for VR-2026-001"]',
    );

    actionButton!.click();
    fixture.detectChanges();
    await fixture.whenStable();

    menuItemByText('Details').click();
    fixture.detectChanges();
    await fixture.whenStable();

    expect(navigateSpy).toHaveBeenCalledWith([
      '/p/collections/proposals/my-assignments',
      PROPOSAL.id,
    ]);
  });

  it('forwards an assignment from the confirmation modal', async () => {
    const fixture = TestBed.createComponent(ProposalsMyAssignmentsPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const component = fixture.componentInstance as unknown as {
      openForwardModal(proposalId: string): void;
    };
    const compiled = fixture.nativeElement as HTMLElement;

    component.openForwardModal('proposal-1');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const dialog = compiled.querySelector<HTMLElement>('[role="dialog"]');
    const select = compiled.querySelector<HTMLSelectElement>('#forward-modal-target');
    const note = compiled.querySelector<HTMLTextAreaElement>('#forward-modal-note');
    const submit = Array.from(compiled.querySelectorAll<HTMLButtonElement>('button')).find(
      (button) => button.textContent?.trim() === 'Forward',
    );

    expect(dialog).not.toBeNull();
    expect(dialog!.textContent).toContain('VR-2026-001');
    expect(select).not.toBeNull();
    expect(note).not.toBeNull();
    expect(submit).not.toBeNull();
    expect(submit!.disabled).toBe(true);

    select!.value = 'permission-curatorial';
    select!.dispatchEvent(new Event('change'));
    note!.value = 'Please review the curatorial aspects.';
    note!.dispatchEvent(new Event('input'));
    fixture.detectChanges();

    expect(submit!.disabled).toBe(false);

    submit!.click();
    fixture.detectChanges();
    await fixture.whenStable();
    await new Promise<void>((resolve) => setTimeout(resolve));
    fixture.detectChanges();

    expect(proposalService.forwardCalls).toEqual([
      {
        proposalId: 'proposal-1',
        payload: {
          targetPermissionId: 'permission-curatorial',
          note: 'Please review the curatorial aspects.',
        },
      },
    ]);
    expect(compiled.textContent).toContain('Assignment forwarded');
    expect(compiled.textContent).toContain('VR-2026-001 was forwarded to Carol Lima');
  });
});

function menuItemByText(text: string): HTMLElement {
  const item = Array.from(
    document.body.querySelectorAll<HTMLElement>('.p-menu a, .p-menu button'),
  ).find((candidate) => candidate.textContent?.trim() === text);

  if (!(item instanceof HTMLElement)) {
    throw new Error(`Menu item not found: ${text}`);
  }

  return item;
}
