import { HttpErrorResponse } from '@angular/common/http';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { of, throwError } from 'rxjs';

import { PermissionPrincipal } from '@core/auth/models/permission.model';
import { ProposalEvent, ProposalDetail, UpdateProposalResult } from '../../models/proposal.model';
import { UpdateProposalRequest } from '../../models/proposal-actions.model';
import { PROPOSAL_API_SERVICE } from '../../services/proposal-api.service';
import { ProposalEditPageComponent } from './proposal-edit-page.component';

const STAFF: PermissionPrincipal = {
  permissionId: 'permission-staff',
  user: { id: 'staff-1', name: 'Bob Santos', email: 'bob@example.test' },
  group: 'COLLECTIONS_MANAGEMENT',
};

const LAST_EVENT: ProposalEvent = {
  occurredAt: '2026-05-02T10:00:00Z',
  type: 'ASSIGNED',
  triggeredBy: STAFF,
  note: null,
};

const PROPOSAL: ProposalDetail = {
  id: 'proposal-1',
  referenceNumber: 'VRP-20260601-0001',
  title: 'Atlantic forest catalogue study',
  status: 'PENDING',
  type: 'IN_SITU_VISIT',
  intendedUse: {
    useType: 'IN_SITU_VISIT',
    description: 'On-site research using specimen catalogues.',
  },
  beginDate: '2026-07-01',
  endDate: '2026-12-31',
  requestedBy: {
    permissionId: 'permission-requester',
    user: { id: 'user-1', name: 'Alice Ferreira', email: 'alice@example.test' },
    group: 'EXTERNAL',
  },
  assignedTo: STAFF,
  submittedAt: '2026-05-01T10:00:00Z',
  conversationId: 'conversation-1',
  documents: [],
  requestedObjects: [],
};

class ProposalApiServiceStub {
  proposal = structuredClone(PROPOSAL);
  readonly updateCalls: { proposalId: string; request: UpdateProposalRequest }[] = [];
  updateError: HttpErrorResponse | null = null;

  getProposal() {
    return of(this.proposal);
  }

  updateProposal(proposalId: string, request: UpdateProposalRequest) {
    this.updateCalls.push({ proposalId, request });
    if (this.updateError) return throwError(() => this.updateError);

    const result: UpdateProposalResult = {
      id: proposalId,
      referenceNumber: this.proposal.referenceNumber,
      title: request.title === undefined ? this.proposal.title : request.title,
      status: this.proposal.status,
      beginDate:
        request.beginDate === undefined ? (this.proposal.beginDate ?? null) : request.beginDate,
      endDate: request.endDate === undefined ? (this.proposal.endDate ?? null) : request.endDate,
      lastEvent: LAST_EVENT,
    };
    return of(result);
  }
}

describe('ProposalEditPageComponent', () => {
  let fixture: ComponentFixture<ProposalEditPageComponent>;
  let service: ProposalApiServiceStub;
  let router: Router;

  beforeEach(async () => {
    service = new ProposalApiServiceStub();
    await TestBed.configureTestingModule({
      imports: [ProposalEditPageComponent],
      providers: [provideRouter([]), { provide: PROPOSAL_API_SERVICE, useValue: service }],
    }).compileComponents();

    router = TestBed.inject(Router);
  });

  async function render(): Promise<HTMLElement> {
    fixture = TestBed.createComponent(ProposalEditPageComponent);
    fixture.componentRef.setInput('id', 'proposal-1');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  it('loads the editable proposal metadata into the form', async () => {
    const compiled = await render();

    expect(input(compiled, 'proposal-edit-title').value).toBe('Atlantic forest catalogue study');
    expect(select(compiled, 'proposal-edit-use-type').value).toBe('IN_SITU_VISIT');
    expect(textarea(compiled, 'proposal-edit-use-description').value).toContain('On-site research');
    expect(input(compiled, 'proposal-edit-begin-date').value).toBe('2026-07-01');
    expect(button(compiled, 'Save changes').disabled).toBe(true);
  });

  it('sends only changed fields and returns to a freshly loaded detail route', async () => {
    const compiled = await render();
    const navigate = vi.spyOn(router, 'navigate').mockResolvedValue(true);

    change(input(compiled, 'proposal-edit-title'), 'Revised catalogue study');
    fixture.detectChanges();
    button(compiled, 'Save changes').click();
    await fixture.whenStable();

    expect(service.updateCalls).toEqual([
      {
        proposalId: 'proposal-1',
        request: { title: 'Revised catalogue study' },
      },
    ]);
    expect(navigate).toHaveBeenCalledWith([
      '/p/collections/proposals/my-assignments',
      'proposal-1',
    ]);
  });

  it('maps cleared nullable fields to explicit null', async () => {
    const compiled = await render();
    vi.spyOn(router, 'navigate').mockResolvedValue(true);

    change(input(compiled, 'proposal-edit-title'), '');
    change(input(compiled, 'proposal-edit-end-date'), '');
    fixture.detectChanges();
    button(compiled, 'Save changes').click();
    await fixture.whenStable();

    expect(service.updateCalls[0]?.request).toEqual({ title: null, endDate: null });
  });

  it('replaces intended use atomically and prevents an invalid date range', async () => {
    const compiled = await render();

    change(select(compiled, 'proposal-edit-use-type'), 'EXHIBITION');
    change(textarea(compiled, 'proposal-edit-use-description'), 'Public exhibition.');
    change(input(compiled, 'proposal-edit-end-date'), '2026-01-01');
    fixture.detectChanges();

    expect(compiled.textContent).toContain('End date cannot precede begin date.');
    expect(button(compiled, 'Save changes').disabled).toBe(true);

    change(input(compiled, 'proposal-edit-end-date'), '2026-10-01');
    fixture.detectChanges();
    vi.spyOn(router, 'navigate').mockResolvedValue(true);
    button(compiled, 'Save changes').click();
    await fixture.whenStable();

    expect(service.updateCalls[0]?.request).toEqual({
      intendedUse: { useType: 'EXHIBITION', description: 'Public exhibition.' },
      endDate: '2026-10-01',
    });
  });

  it('blocks terminal proposals and keeps API failures on the page', async () => {
    service.proposal = { ...structuredClone(PROPOSAL), status: 'APPROVED' };
    let compiled = await render();

    expect(compiled.textContent).toContain('This proposal can no longer be edited');
    expect(compiled.querySelector('form')).toBeNull();

    fixture.destroy();
    service.proposal = structuredClone(PROPOSAL);
    service.updateError = new HttpErrorResponse({
      status: 422,
      error: { message: 'endDate must be after beginDate' },
    });
    compiled = await render();
    change(input(compiled, 'proposal-edit-title'), 'Another title');
    fixture.detectChanges();
    button(compiled, 'Save changes').click();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(compiled.textContent).toContain('endDate must be after beginDate');
    expect(input(compiled, 'proposal-edit-title').value).toBe('Another title');
  });
});

function input(root: HTMLElement, id: string): HTMLInputElement {
  return root.querySelector<HTMLInputElement>(`#${id}`)!;
}

function select(root: HTMLElement, id: string): HTMLSelectElement {
  return root.querySelector<HTMLSelectElement>(`#${id}`)!;
}

function textarea(root: HTMLElement, id: string): HTMLTextAreaElement {
  return root.querySelector<HTMLTextAreaElement>(`#${id}`)!;
}

function button(root: HTMLElement, text: string): HTMLButtonElement {
  return Array.from(root.querySelectorAll<HTMLButtonElement>('button')).find((candidate) =>
    candidate.textContent?.includes(text),
  )!;
}

function change(
  element: HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement,
  value: string,
): void {
  element.value = value;
  element.dispatchEvent(new Event('input', { bubbles: true }));
}
