import { Router, provideRouter } from '@angular/router';
import { TestBed } from '@angular/core/testing';
import { computed, signal } from '@angular/core';
import { of } from 'rxjs';

import { IDENTITY_SERVICE, IdentityService } from '@core/auth/identity.service';
import { GroupName } from '@core/auth/models/group-name.enum';
import { IdentitySession } from '@core/auth/models/identity-session.model';
import { LoginRequest } from '@core/auth/models/login.model';
import { Page } from '@shared/models/page.model';

import { ProposalListQuery, ProposalSummary } from '../../models/proposal.model';
import { PROPOSAL_API_SERVICE } from '../../services/proposal-api.service';
import { ProposalsMyPageComponent } from './proposals-my-page.component';

const EXTERNAL_SESSION: IdentitySession = {
  accessToken: 'token',
  user: {
    id: 'user-1',
    email: 'alice@example.test',
    displayName: 'Alice Ferreira',
  },
  group: 'EXTERNAL',
  availableGroups: ['EXTERNAL'],
  permissions: [{ permissionId: 'permission-external', group: 'EXTERNAL' }],
};

const STAFF_SESSION: IdentitySession = {
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
  status: 'SUBMITTED',
  type: 'IN_SITU_VISIT',
  requestedBy: {
    permissionId: 'permission-external',
    user: { id: 'user-1', name: 'Alice Ferreira', email: 'alice@example.test' },
    group: 'EXTERNAL',
  },
  assignedTo: null,
  collectionUseProject: {
    id: 'project-1',
    referenceNumber: 'VR-2026-001',
    title: 'Photographic history of Rio de Janeiro port, 1890-1930',
    status: 'CREATED',
  },
  submittedAt: '2026-05-01T10:00:00',
};

let activeSession: IdentitySession = EXTERNAL_SESSION;

class IdentityServiceStub implements IdentityService {
  private readonly sessionState = signal<IdentitySession | null>(activeSession);

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
    return session?.permissions?.find((p) => p.group === session.group)?.permissionId ?? null;
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
  readonly cancelCalls: { proposalId: string; reason: string }[] = [];
  rows: ProposalSummary[] = [PROPOSAL];

  listProposals(query: ProposalListQuery = {}) {
    this.queries.push(query);
    const size = query.size ?? 20;
    const page = query.page ?? 0;
    const start = page * size;

    return of<Page<ProposalSummary>>({
      content: this.rows.slice(start, start + size),
      page,
      size,
      totalElements: this.rows.length,
      totalPages: this.rows.length === 0 ? 0 : Math.ceil(this.rows.length / size),
    });
  }

  cancelProposal(proposalId: string, request: { reason: string }) {
    this.cancelCalls.push({ proposalId, reason: request.reason });
    return of({
      proposal: {
        id: proposalId,
        referenceNumber: PROPOSAL.referenceNumber,
        title: PROPOSAL.title,
        status: 'CANCELLED' as const,
        assignedTo: null,
        lastEvent: {
          occurredAt: '2026-05-02T10:00:00',
          type: 'CANCELLED' as const,
          triggeredBy: PROPOSAL.requestedBy,
          note: request.reason,
        },
      },
      collectionUseProject: null,
    });
  }
}

describe('ProposalsMyPageComponent', () => {
  let proposalService: ProposalApiServiceStub;
  let router: Router;

  beforeEach(async () => {
    activeSession = EXTERNAL_SESSION;
    proposalService = new ProposalApiServiceStub();

    await TestBed.configureTestingModule({
      imports: [ProposalsMyPageComponent],
      providers: [
        provideRouter([]),
        { provide: IDENTITY_SERVICE, useClass: IdentityServiceStub },
        { provide: PROPOSAL_API_SERVICE, useValue: proposalService },
      ],
    }).compileComponents();

    router = TestBed.inject(Router);
  });

  it('queries proposals by requestedBy for any group', async () => {
    const fixture = TestBed.createComponent(ProposalsMyPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(proposalService.queries.at(-1)).toMatchObject({
      requestedBy: 'permission-external',
      page: 0,
      size: 20,
      search: '',
    });
    expect(proposalService.queries.at(-1)).not.toHaveProperty('assignedTo');
    expect(proposalService.queries.at(-1)).not.toHaveProperty('lifecyclePhase');
  });

  it('also queries by requestedBy for staff groups', async () => {
    activeSession = STAFF_SESSION;

    const fixture = TestBed.createComponent(ProposalsMyPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(proposalService.queries.at(-1)).toMatchObject({
      requestedBy: 'permission-staff',
    });
    expect(proposalService.queries.at(-1)).not.toHaveProperty('assignedTo');
  });

  it('renders the proposals list with a link to the generic detail page', async () => {
    const fixture = TestBed.createComponent(ProposalsMyPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;

    expect(compiled.querySelector('#proposals-search')).not.toBeNull();
    expect(compiled.textContent).toContain('My proposals');
    expect(compiled.textContent).toContain('Reference');
    expect(compiled.querySelector('a[href^="/p/collections/proposals/proposal-1"]')).not.toBeNull();
    expect(compiled.querySelector('a[href^="/p/collections/proposals/my/proposal-1"]')).toBeNull();
    expect(compiled.querySelector('[aria-label="More actions for VR-2026-001"]')).not.toBeNull();
  });

  it('navigates to the generic detail page with returnTo on view details', async () => {
    const navigateSpy = vi.spyOn(router, 'navigate').mockResolvedValue(true);

    const fixture = TestBed.createComponent(ProposalsMyPageComponent);
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

    expect(navigateSpy).toHaveBeenCalledWith(['/p/collections/proposals', PROPOSAL.id], {
      queryParams: {
        returnTo: '/p/collections/proposals/my',
        returnLabel: 'my proposals',
      },
    });
  });

  it('does not show a Forward action in the row menu', async () => {
    const fixture = TestBed.createComponent(ProposalsMyPageComponent);
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

    expect(document.body.textContent).not.toContain('Forward');
    expect(document.body.textContent).toContain('Details');
  });

  it('offers Cancel proposal for a cancellable proposal and submits the reason', async () => {
    const fixture = TestBed.createComponent(ProposalsMyPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    compiled
      .querySelector<HTMLButtonElement>('[aria-label="More actions for VR-2026-001"]')!
      .click();
    fixture.detectChanges();
    await fixture.whenStable();

    menuItemByText('Cancel proposal').click();
    fixture.detectChanges();
    await fixture.whenStable();

    const reason = compiled.querySelector<HTMLTextAreaElement>('#cancel-reason');
    expect(reason).not.toBeNull();
    reason!.value = 'Trip cancelled';
    reason!.dispatchEvent(new Event('input'));
    fixture.detectChanges();

    const confirmButton = Array.from(
      compiled.querySelectorAll<HTMLButtonElement>('.confirm-modal__button--primary'),
    ).find((button) => button.textContent?.includes('Cancel proposal'));
    confirmButton!.click();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(proposalService.cancelCalls).toEqual([
      { proposalId: 'proposal-1', reason: 'Trip cancelled' },
    ]);
  });

  it('advances to the next page and re-queries with the new page index', async () => {
    proposalService.rows = Array.from({ length: 45 }, (_, i) => ({
      ...PROPOSAL,
      id: `proposal-${i + 1}`,
      referenceNumber: `VR-2026-${String(i + 1).padStart(3, '0')}`,
    }));

    const fixture = TestBed.createComponent(ProposalsMyPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.textContent).toContain('Page 1 of 3');

    compiled.querySelector<HTMLButtonElement>('[aria-label="Next page"]')!.click();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(proposalService.queries.at(-1)).toMatchObject({ page: 1, size: 20 });
    expect(compiled.textContent).toContain('Page 2 of 3');
  });

  it('reflects the default page size in the Rows select and re-queries when it changes', async () => {
    proposalService.rows = Array.from({ length: 15 }, (_, i) => ({
      ...PROPOSAL,
      id: `proposal-${i + 1}`,
      referenceNumber: `VR-2026-${String(i + 1).padStart(3, '0')}`,
    }));

    const fixture = TestBed.createComponent(ProposalsMyPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    const select = compiled.querySelector<HTMLSelectElement>('#proposals-page-size')!;

    // The select must show the actual model size (20), not its first option (10).
    expect(select.value).toBe('20');
    expect(proposalService.queries.at(-1)).toMatchObject({ size: 20, page: 0 });

    select.value = '10';
    select.dispatchEvent(new Event('change'));
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(proposalService.queries.at(-1)).toMatchObject({ size: 10, page: 0 });
    expect(compiled.textContent).toContain('Page 1 of 2');
  });

  it('hides Cancel proposal for terminal proposals', async () => {
    proposalService.rows = [{ ...PROPOSAL, status: 'REJECTED' }];

    const fixture = TestBed.createComponent(ProposalsMyPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    compiled
      .querySelector<HTMLButtonElement>('[aria-label="More actions for VR-2026-001"]')!
      .click();
    fixture.detectChanges();
    await fixture.whenStable();

    expect(document.body.textContent).toContain('Details');
    expect(document.body.textContent).not.toContain('Cancel proposal');
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
