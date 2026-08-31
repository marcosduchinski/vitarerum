import { ComponentRef } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { of } from 'rxjs';

import { IDENTITY_SERVICE } from '@core/auth/identity.service';
import { UserDetail } from '@core/auth/models/user.model';
import { USER_MANAGEMENT_SERVICE } from '@features/admin/services/user-management.service';
import { Page } from '@shared/models/page.model';

import { ProposalDetail, ProposalEventsPage } from '../../models/proposal.model';
import { PROPOSAL_API_SERVICE } from '../../services/proposal-api.service';
import { ProposalDirectionDetailPageComponent } from './proposal-direction-detail-page.component';

const PROPOSAL: ProposalDetail = {
  id: 'proposal-1',
  referenceNumber: 'VRP-20260831-0001',
  title: 'Direction review',
  status: 'PENDING',
  submissionChannel: 'AUTHENTICATED',
  type: 'IN_SITU_VISIT',
  requestedBy: {
    permissionId: 'permission-external',
    user: { id: 'external-1', name: 'Alice', email: 'alice@example.test' },
    group: 'EXTERNAL',
  },
  assignedTo: {
    permissionId: 'permission-direction',
    user: { id: 'direction-1', name: 'Diana', email: 'diana@example.test' },
    group: 'DIRECTION',
  },
  submittedAt: '2026-08-31T09:00:00Z',
  conversationId: 'conversation-1',
  documents: [],
  requestedObjects: [],
};

const EVENTS: ProposalEventsPage = {
  proposalId: 'proposal-1',
  content: [
    {
      occurredAt: '2026-08-31T10:00:00Z',
      type: 'REFERRED_TO_DIRECTION',
      triggeredBy: {
        permissionId: 'permission-curator',
        user: { id: 'curator-1', name: 'Carlos', email: 'carlos@example.test' },
        group: 'CURATORIAL',
      },
      targetPermission: PROPOSAL.assignedTo,
      note: 'Strategic decision required',
    },
  ],
  page: 0,
  size: 20,
  totalElements: 1,
  totalPages: 1,
};

const USERS: Page<UserDetail> = {
  content: [
    {
      id: 'curator-1',
      name: 'Carlos',
      email: 'carlos@example.test',
      permissions: [
        {
          permissionId: 'permission-curator',
          group: { id: 'curatorial', name: 'CURATORIAL' },
        },
      ],
    },
    {
      id: 'direction-2',
      name: 'Other Direction member',
      email: 'other@example.test',
      permissions: [
        {
          permissionId: 'permission-direction-2',
          group: { id: 'direction', name: 'DIRECTION' },
        },
      ],
    },
  ],
  page: 0,
  size: 100,
  totalElements: 2,
  totalPages: 1,
};

class ProposalServiceStub {
  readonly returnCalls: { proposalId: string; targetPermissionId: string; reason: string }[] = [];

  getProposal() {
    return of(PROPOSAL);
  }

  listEvents() {
    return of(EVENTS);
  }

  returnProposalToStaff(
    proposalId: string,
    request: { targetPermissionId: string; reason: string },
  ) {
    this.returnCalls.push({ proposalId, ...request });
    return of({ id: proposalId, status: 'PENDING' });
  }
}

describe('ProposalDirectionDetailPageComponent', () => {
  let fixture: ComponentFixture<ProposalDirectionDetailPageComponent>;
  let service: ProposalServiceStub;

  beforeEach(async () => {
    service = new ProposalServiceStub();
    await TestBed.configureTestingModule({
      imports: [ProposalDirectionDetailPageComponent],
      providers: [
        provideRouter([]),
        { provide: PROPOSAL_API_SERVICE, useValue: service },
        { provide: USER_MANAGEMENT_SERVICE, useValue: { listUsers: () => of(USERS) } },
        {
          provide: IDENTITY_SERVICE,
          useValue: { getPermissionId: () => 'permission-direction' },
        },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(ProposalDirectionDetailPageComponent);
    const componentRef: ComponentRef<ProposalDirectionDetailPageComponent> = fixture.componentRef;
    componentRef.setInput('id', 'proposal-1');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
  });

  it('exposes the dedicated read-only tab set without Messages', () => {
    const root = fixture.nativeElement as HTMLElement;
    const tabs = Array.from(root.querySelectorAll('[role="tab"]')).map((tab) =>
      tab.textContent?.trim(),
    );

    expect(tabs).toEqual(['Overview', 'Event Log', 'Documents', 'Objects', 'Actions']);
    expect(root.textContent).not.toContain('Messages');
  });

  it('requires a response and returns only to an operational staff member', async () => {
    const root = fixture.nativeElement as HTMLElement;
    const router = TestBed.inject(Router);
    const navigate = vi.spyOn(router, 'navigate').mockResolvedValue(true);
    clickTab(root, 'Actions');
    fixture.detectChanges();
    buttonByText(root, 'Return to the Staff').click();
    fixture.detectChanges();

    const confirm = root.querySelector<HTMLButtonElement>('.confirm-modal__button--primary')!;
    expect(confirm.disabled).toBe(true);
    const select = root.querySelector<HTMLSelectElement>('#return-target')!;
    expect(Array.from(select.options).map((option) => option.value)).toEqual([
      '',
      'permission-curator',
    ]);
    select.value = 'permission-curator';
    select.dispatchEvent(new Event('change'));
    const reason = root.querySelector<HTMLTextAreaElement>('#return-reason')!;
    reason.value = ' Please revise the insurance conditions ';
    reason.dispatchEvent(new Event('input'));
    fixture.detectChanges();
    expect(confirm.disabled).toBe(false);

    confirm.click();
    fixture.detectChanges();
    await fixture.whenStable();

    expect(service.returnCalls).toEqual([
      {
        proposalId: 'proposal-1',
        targetPermissionId: 'permission-curator',
        reason: 'Please revise the insurance conditions',
      },
    ]);
    expect(navigate).toHaveBeenCalledWith(['/p/collections/proposals/my-assignments']);
  });
});

function clickTab(root: HTMLElement, label: string): void {
  buttonByText(root, label).click();
}

function buttonByText(root: HTMLElement, label: string): HTMLButtonElement {
  const button = Array.from(root.querySelectorAll<HTMLButtonElement>('button')).find(
    (candidate) => candidate.textContent?.trim() === label,
  );
  if (button === undefined) throw new Error(`Button not found: ${label}`);
  return button;
}
