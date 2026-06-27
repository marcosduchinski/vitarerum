import { IDENTITY_SERVICE } from '@core/auth/identity.service';
import { IdentityServiceMock } from '@core/auth/identity.service.mock';
import { TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { of } from 'rxjs';

import { Page } from '@shared/models/page.model';

import { ProposalListQuery, ProposalSummary } from '../../models/proposal.model';
import { PROPOSAL_API_SERVICE } from '../../services/proposal-api.service';
import { ProposalsRejectedPageComponent } from './proposals-rejected-page.component';

const REJECTED_PROPOSAL: ProposalSummary = {
  id: 'proposal-rejected',
  referenceNumber: 'VR-2026-001',
  title: 'Rejected research request',
  status: 'REJECTED',
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
    title: 'Rejected research request',
    status: 'CANCELLED',
  },
  submittedAt: '2026-05-01T10:00:00',
};

const CANCELLED_PROPOSAL: ProposalSummary = {
  ...REJECTED_PROPOSAL,
  id: 'proposal-cancelled',
  referenceNumber: 'VR-2026-002',
  title: 'Cancelled research request',
  status: 'CANCELLED',
  submittedAt: '2026-05-02T10:00:00',
};

class ProposalApiServiceStub {
  readonly queries: ProposalListQuery[] = [];

  listProposals(query: ProposalListQuery = {}) {
    this.queries.push(query);
    const size = query.size ?? 20;
    const statuses = typeof query.status === 'string' ? [query.status] : (query.status ?? []);
    const content = [REJECTED_PROPOSAL, CANCELLED_PROPOSAL].filter((proposal) =>
      statuses.includes(proposal.status),
    );

    return of<Page<ProposalSummary>>({
      content,
      page: query.page ?? 0,
      size,
      totalElements: content.length,
      totalPages: content.length ? 1 : 0,
    });
  }
}

describe('ProposalsRejectedPageComponent', () => {
  let proposalService: ProposalApiServiceStub;
  let router: Router;

  beforeEach(async () => {
    proposalService = new ProposalApiServiceStub();

    await TestBed.configureTestingModule({
      imports: [ProposalsRejectedPageComponent],
      providers: [
        { provide: IDENTITY_SERVICE, useClass: IdentityServiceMock },

        provideRouter([]),
        { provide: PROPOSAL_API_SERVICE, useValue: proposalService },
      ],
    }).compileComponents();

    router = TestBed.inject(Router);
  });

  afterEach(() => {
    document.querySelectorAll('.p-menu').forEach((element) => element.remove());
  });

  it('fetches rejected and cancelled proposals', async () => {
    const fixture = TestBed.createComponent(ProposalsRejectedPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(proposalService.queries).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          status: ['REJECTED', 'CANCELLED'],
          page: 0,
          size: 100,
          search: '',
        }),
      ]),
    );
  });

  it('renders rejected proposals with status chips and a row menu', async () => {
    const fixture = TestBed.createComponent(ProposalsRejectedPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;

    expect(compiled.querySelector('#proposals-search')).not.toBeNull();
    expect(compiled.textContent).toContain('Rejected research request');
    expect(compiled.textContent).toContain('Cancelled research request');
    expect(compiled.textContent).toContain('Rejected');
    expect(compiled.textContent).toContain('Cancelled');
    expect(compiled.querySelector('[aria-label="More actions for VR-2026-001"]')).not.toBeNull();
  });

  it('opens the row menu and navigates to the rejected proposal detail', async () => {
    const navigateSpy = vi.spyOn(router, 'navigate').mockResolvedValue(true);
    const fixture = TestBed.createComponent(ProposalsRejectedPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    (fixture.nativeElement as HTMLElement)
      .querySelector<HTMLButtonElement>('[aria-label="More actions for VR-2026-001"]')!
      .click();
    fixture.detectChanges();
    await fixture.whenStable();

    const details = Array.from(
      document.body.querySelectorAll<HTMLElement>('.p-menu a, .p-menu button'),
    ).find((item) => item.textContent?.trim() === 'Details');
    details!.click();

    expect(navigateSpy).toHaveBeenCalledWith([
      '/p/collections/proposals/rejected',
      'proposal-rejected',
    ]);
  });
});
