import { IDENTITY_SERVICE } from '@core/auth/identity.service';
import { IdentityServiceMock } from '@core/auth/identity.service.mock';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of } from 'rxjs';

import { Page } from '@shared/models/page.model';

import { ProposalListQuery, ProposalSummary } from '../../models/proposal.model';
import { PROPOSAL_API_SERVICE } from '../../services/proposal-api.service';
import { ProposalsApprovedPageComponent } from './proposals-approved-page.component';

const APPROVED_PROPOSAL: ProposalSummary = {
  id: 'proposal-approved',
  referenceNumber: 'VR-2026-001',
  title: 'Approved research request',
  status: 'APPROVED',
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
    title: 'Approved research request',
    status: 'CREATED',
  },
  submittedAt: '2026-05-01T10:00:00',
};

// An approved proposal whose project link the backend has not materialised/embedded.
const APPROVED_PROPOSAL_WITHOUT_PROJECT: ProposalSummary = {
  ...APPROVED_PROPOSAL,
  id: 'proposal-no-project',
  referenceNumber: 'VR-2026-002',
  collectionUseProject: undefined,
};

class ProposalApiServiceStub {
  readonly queries: ProposalListQuery[] = [];
  content: ProposalSummary[] = [APPROVED_PROPOSAL];

  listProposals(query: ProposalListQuery = {}) {
    this.queries.push(query);
    const size = query.size ?? 20;

    return of<Page<ProposalSummary>>({
      content: this.content,
      page: query.page ?? 0,
      size,
      totalElements: this.content.length,
      totalPages: 1,
    });
  }
}

describe('ProposalsApprovedPageComponent', () => {
  let proposalService: ProposalApiServiceStub;

  beforeEach(async () => {
    proposalService = new ProposalApiServiceStub();

    await TestBed.configureTestingModule({
      imports: [ProposalsApprovedPageComponent],
      providers: [
        { provide: IDENTITY_SERVICE, useClass: IdentityServiceMock },

        provideRouter([]),
        { provide: PROPOSAL_API_SERVICE, useValue: proposalService },
      ],
    }).compileComponents();
  });

  it('lists approved proposals with the approved status filter', async () => {
    const fixture = TestBed.createComponent(ProposalsApprovedPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(proposalService.queries.at(-1)).toMatchObject({
      status: 'APPROVED',
      page: 0,
      size: 20,
      search: '',
    });
  });

  it('renders the terminal proposal table, status, and row action trigger', async () => {
    const fixture = TestBed.createComponent(ProposalsApprovedPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;

    expect(compiled.querySelector('#proposals-search')).not.toBeNull();
    expect(compiled.textContent).toContain('Reference');
    expect(compiled.textContent).toContain('Assigned to');
    expect(compiled.textContent).toContain('Approved');
    expect(compiled.textContent).toContain('Approved research request');
    expect(compiled.querySelector('[aria-label="More actions for VR-2026-001"]')).not.toBeNull();
  });

  it('shows proposal and project actions in the row menu', async () => {
    const fixture = TestBed.createComponent(ProposalsApprovedPageComponent);
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

    expect(document.body.textContent).toContain('Details');
    expect(document.body.textContent).toContain('Go to project');
  });

  it('opens the row menu without a project link when the proposal has no project', async () => {
    proposalService.content = [APPROVED_PROPOSAL_WITHOUT_PROJECT];

    const fixture = TestBed.createComponent(ProposalsApprovedPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    const actionButton = compiled.querySelector<HTMLButtonElement>(
      '[aria-label="More actions for VR-2026-002"]',
    );

    expect(actionButton).not.toBeNull();

    // Must not throw on a proposal whose collectionUseProject is absent.
    actionButton!.click();
    fixture.detectChanges();
    await fixture.whenStable();

    expect(document.body.textContent).toContain('Details');
    expect(document.body.textContent).not.toContain('Go to project');
  });
});
