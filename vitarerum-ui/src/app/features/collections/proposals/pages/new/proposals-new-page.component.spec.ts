import { provideRouter, Router } from '@angular/router';
import { TestBed } from '@angular/core/testing';
import { of } from 'rxjs';

import { UserDetail } from '@core/auth/models/user.model';
import { USER_MANAGEMENT_SERVICE } from '@features/admin/services/user-management.service';
import { Page } from '@shared/models/page.model';

import { ProposalListQuery, ProposalSummary } from '../../models/proposal.model';
import { PROPOSAL_API_SERVICE } from '../../services/proposal-api.service';
import { ProposalsNewPageComponent } from './proposals-new-page.component';

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

class ProposalApiServiceStub {
  readonly queries: ProposalListQuery[] = [];
  readonly assignCalls: {
    readonly proposalId: string;
    readonly payload: { readonly targetPermissionId?: string; readonly note: string };
  }[] = [];

  listProposals(query: ProposalListQuery = {}) {
    this.queries.push(query);
    const size = query.size ?? 20;
    const totalElements = query.search === 'missing' ? 0 : 75;

    return of<Page<ProposalSummary>>({
      content: totalElements ? [PROPOSAL] : [],
      page: query.page ?? 0,
      size,
      totalElements,
      totalPages: Math.ceil(totalElements / size),
    });
  }

  assignProposal(
    proposalId: string,
    payload: { readonly targetPermissionId?: string; readonly note: string },
  ) {
    this.assignCalls.push({ proposalId, payload });
    return of({ id: PROPOSAL.id, status: 'PENDING', assignedTo: null, lastEvent: null });
  }
}

class UserManagementServiceStub {
  listUsers() {
    return of(STAFF_USERS);
  }
}

describe('ProposalsNewPageComponent', () => {
  let proposalService: ProposalApiServiceStub;

  beforeEach(async () => {
    proposalService = new ProposalApiServiceStub();

    await TestBed.configureTestingModule({
      imports: [ProposalsNewPageComponent],
      providers: [
        provideRouter([]),
        { provide: PROPOSAL_API_SERVICE, useValue: proposalService },
        { provide: USER_MANAGEMENT_SERVICE, useClass: UserManagementServiceStub },
      ],
    }).compileComponents();
  });

  it('applies and clears search through signal-backed resource params', async () => {
    const fixture = TestBed.createComponent(ProposalsNewPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    const searchInput = compiled.querySelector<HTMLInputElement>('#proposals-search');

    expect(searchInput).not.toBeNull();

    searchInput!.value = 'Rio';
    searchInput!.dispatchEvent(new Event('input'));
    fixture.detectChanges();

    compiled.querySelector<HTMLButtonElement>('.proposals-toolbar .action-btn--primary')?.click();
    fixture.detectChanges();
    await fixture.whenStable();

    expect(proposalService.queries.at(-1)).toMatchObject({ page: 0, size: 20, search: 'Rio' });

    compiled.querySelector<HTMLButtonElement>('.proposals-search__clear')?.click();
    fixture.detectChanges();
    await fixture.whenStable();

    expect(proposalService.queries.at(-1)).toMatchObject({ page: 0, size: 20, search: '' });
  });

  it('resets to the first page when page size changes', async () => {
    const fixture = TestBed.createComponent(ProposalsNewPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    buttonByText(fixture.nativeElement, 'Next').click();
    fixture.detectChanges();
    await fixture.whenStable();

    expect(proposalService.queries.at(-1)).toMatchObject({ page: 1, size: 20 });

    const pageSize = (fixture.nativeElement as HTMLElement).querySelector<HTMLSelectElement>(
      '#proposals-page-size',
    );
    expect(pageSize).not.toBeNull();

    pageSize!.value = '50';
    pageSize!.dispatchEvent(new Event('change'));
    fixture.detectChanges();
    await fixture.whenStable();

    expect(proposalService.queries.at(-1)).toMatchObject({ page: 0, size: 50 });
  });

  it('keeps pagination controls within valid page boundaries', async () => {
    const fixture = TestBed.createComponent(ProposalsNewPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    buttonByText(fixture.nativeElement, 'Last').click();
    fixture.detectChanges();
    await fixture.whenStable();

    expect(proposalService.queries.at(-1)).toMatchObject({ page: 3, size: 20 });

    buttonByText(fixture.nativeElement, 'Next').click();
    fixture.detectChanges();
    await fixture.whenStable();

    expect(proposalService.queries.at(-1)).toMatchObject({ page: 3, size: 20 });

    buttonByText(fixture.nativeElement, 'First').click();
    fixture.detectChanges();
    await fixture.whenStable();

    expect(proposalService.queries.at(-1)).toMatchObject({ page: 0, size: 20 });
    expect(buttonByText(fixture.nativeElement, 'Previous').disabled).toBe(true);
  });

  it('keeps search controls visible when a search has no results', async () => {
    const fixture = TestBed.createComponent(ProposalsNewPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    const searchInput = compiled.querySelector<HTMLInputElement>('#proposals-search');

    searchInput!.value = 'missing';
    searchInput!.dispatchEvent(new Event('input'));
    fixture.detectChanges();
    compiled.querySelector<HTMLButtonElement>('.proposals-toolbar .action-btn--primary')?.click();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(compiled.querySelector('#proposals-search')).not.toBeNull();
    expect(compiled.textContent).toContain('No proposals found');
  });

  it('confirms assuming a new proposal then redirects to the assignment detail', async () => {
    const router = TestBed.inject(Router);
    const navigateSpy = vi.spyOn(router, 'navigate').mockResolvedValue(true);

    const fixture = TestBed.createComponent(ProposalsNewPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;

    buttonByText(compiled, 'Assign to me').click();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(proposalService.assignCalls).toEqual([]);
    expect(compiled.textContent).toContain('Assign to me?');
    expect(compiled.textContent).toContain('This will assign VR-2026-001 to you for review.');

    compiled.querySelector<HTMLButtonElement>('.confirm-modal__button--primary')!.click();
    fixture.detectChanges();
    await fixture.whenStable();

    expect(proposalService.assignCalls).toEqual([
      {
        proposalId: 'proposal-1',
        payload: { note: '' },
      },
    ]);
    expect(navigateSpy).toHaveBeenCalledWith([
      '/p/collections/proposals/my-assignments',
      'proposal-1',
    ]);
  });

  it('forwards a new proposal from the confirmation modal', async () => {
    const fixture = TestBed.createComponent(ProposalsNewPageComponent);
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

    expect(compiled.querySelector('.forward-panel-row')).toBeNull();
    expect(dialog).not.toBeNull();
    expect(dialog!.textContent).toContain('VR-2026-001');
    expect(select).not.toBeNull();
    expect(note).not.toBeNull();
    expect(submit).not.toBeNull();
    expect(submit!.disabled).toBe(true);

    select!.value = 'permission-staff';
    select!.dispatchEvent(new Event('change'));
    note!.value = 'Please review this incoming request.';
    note!.dispatchEvent(new Event('input'));
    fixture.detectChanges();

    expect(submit!.disabled).toBe(false);

    submit!.click();
    fixture.detectChanges();
    await fixture.whenStable();
    await new Promise<void>((resolve) => setTimeout(resolve));
    fixture.detectChanges();

    expect(proposalService.assignCalls).toEqual([
      {
        proposalId: 'proposal-1',
        payload: {
          targetPermissionId: 'permission-staff',
          note: 'Please review this incoming request.',
        },
      },
    ]);
    expect(compiled.textContent).toContain('Proposal forwarded');
    expect(compiled.textContent).toContain('VR-2026-001 was forwarded to Bob Santos');
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
