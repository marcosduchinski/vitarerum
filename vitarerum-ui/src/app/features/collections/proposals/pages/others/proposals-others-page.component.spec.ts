import { computed, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
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
import { ProposalsOthersPageComponent } from './proposals-others-page.component';

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

const OTHER_PROPOSAL: ProposalSummary = {
  id: 'proposal-other',
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
    permissionId: 'permission-other-staff',
    user: { id: 'staff-2', name: 'Carolina Silva', email: 'carol@example.test' },
    group: 'CURATORIAL',
  },
  collectionUseProject: {
    id: 'project-1',
    referenceNumber: 'VR-2026-001',
    title: 'Photographic history of Rio de Janeiro port, 1890-1930',
    status: 'CREATED',
  },
  submittedAt: '2026-05-01T10:00:00',
};

const MY_PROPOSAL: ProposalSummary = {
  ...OTHER_PROPOSAL,
  id: 'proposal-mine',
  referenceNumber: 'VR-2026-002',
  title: 'Research assigned to Bob',
  assignedTo: {
    permissionId: 'permission-staff',
    user: { id: 'staff-1', name: 'Bob Santos', email: 'bob@example.test' },
    group: 'COLLECTIONS_MANAGEMENT',
  },
  collectionUseProject: {
    ...OTHER_PROPOSAL.collectionUseProject!,
    id: 'project-2',
    referenceNumber: 'VR-2026-002',
    title: 'Research assigned to Bob',
  },
};

const UNASSIGNED_PROPOSAL: ProposalSummary = {
  ...OTHER_PROPOSAL,
  id: 'proposal-unassigned',
  referenceNumber: 'VR-2026-003',
  title: 'Unassigned request',
  assignedTo: null,
  collectionUseProject: {
    ...OTHER_PROPOSAL.collectionUseProject!,
    id: 'project-3',
    referenceNumber: 'VR-2026-003',
    title: 'Unassigned request',
  },
};

const STAFF_USERS: Page<UserDetail> = {
  content: [
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
  ],
  page: 0,
  size: 100,
  totalElements: 1,
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
  readonly queries: ProposalListQuery[] = [];
  readonly assignCalls: {
    readonly proposalId: string;
    readonly payload: { readonly note: string };
  }[] = [];

  listProposals(query: ProposalListQuery = {}) {
    this.queries.push(query);
    const size = query.size ?? 20;

    return of<Page<ProposalSummary>>({
      content: [OTHER_PROPOSAL, MY_PROPOSAL, UNASSIGNED_PROPOSAL],
      page: query.page ?? 0,
      size,
      totalElements: 3,
      totalPages: 1,
    });
  }

  assignProposal(proposalId: string, payload: { readonly note: string }) {
    this.assignCalls.push({ proposalId, payload });
    return of(OTHER_PROPOSAL);
  }
}

class UserManagementServiceStub {
  listUsers() {
    return of(STAFF_USERS);
  }
}

describe('ProposalsOthersPageComponent', () => {
  let proposalService: ProposalApiServiceStub;

  beforeEach(async () => {
    proposalService = new ProposalApiServiceStub();

    await TestBed.configureTestingModule({
      imports: [ProposalsOthersPageComponent],
      providers: [
        provideRouter([]),
        { provide: IDENTITY_SERVICE, useClass: IdentityServiceStub },
        { provide: PROPOSAL_API_SERVICE, useValue: proposalService },
        { provide: USER_MANAGEMENT_SERVICE, useClass: UserManagementServiceStub },
      ],
    }).compileComponents();
  });

  it('fetches assignment candidates and filters out the logged user permission', async () => {
    const fixture = TestBed.createComponent(ProposalsOthersPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;

    expect(proposalService.queries.at(-1)).toMatchObject({
      page: 0,
      size: 100,
      status: 'PENDING',
      search: '',
    });
    expect(compiled.textContent).toContain('Photographic history of Rio de Janeiro port');
    expect(compiled.textContent).toContain('Carolina Silva');
    expect(compiled.textContent).not.toContain('Research assigned to Bob');
    expect(compiled.textContent).not.toContain('Unassigned request');
  });

  it('keeps the search controls and row action trigger in the replicated list', async () => {
    const fixture = TestBed.createComponent(ProposalsOthersPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;

    expect(compiled.querySelector('#proposals-search')).not.toBeNull();
    expect(compiled.textContent).toContain('Reference');
    expect(compiled.textContent).toContain('Requested by');
    expect(compiled.textContent).toContain('Assigned to');
    expect(
      compiled.querySelector('a[href^="/p/collections/proposals/others/proposal-other"]'),
    ).not.toBeNull();
    expect(compiled.querySelector('[aria-label="More actions for VR-2026-001"]')).not.toBeNull();
  });

  it('shows take over and view details in the row menu', async () => {
    const fixture = TestBed.createComponent(ProposalsOthersPageComponent);
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

    expect(document.body.textContent).toContain('Take over');
    expect(document.body.textContent).toContain('Details');
  });

  it('confirms taking over another staff assignment from the row action menu', async () => {
    const fixture = TestBed.createComponent(ProposalsOthersPageComponent);
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

    menuItemByText('Take over').click();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(proposalService.assignCalls).toEqual([]);
    expect(compiled.textContent).toContain('Take over assignment?');
    expect(compiled.textContent).toContain(
      'This will move VR-2026-001 from Carolina Silva to you.',
    );

    buttonByText(compiled, 'Take over assignment').click();
    fixture.detectChanges();
    await fixture.whenStable();

    expect(proposalService.assignCalls).toEqual([
      {
        proposalId: 'proposal-other',
        payload: { note: '' },
      },
    ]);
  });
});

function buttonByText(root: HTMLElement, text: string): HTMLButtonElement {
  const button = Array.from(root.querySelectorAll('button')).find(
    (candidate) => candidate.textContent?.trim() === text,
  );

  if (!(button instanceof HTMLButtonElement)) {
    throw new Error(`Button not found: ${text}`);
  }

  return button;
}

function menuItemByText(text: string): HTMLElement {
  const item = Array.from(document.body.querySelectorAll<HTMLElement>('.p-menu-item-content')).find(
    (candidate) => candidate.textContent?.includes(text),
  );

  if (!item) {
    throw new Error(`Menu item not found: ${text}`);
  }

  return item;
}
