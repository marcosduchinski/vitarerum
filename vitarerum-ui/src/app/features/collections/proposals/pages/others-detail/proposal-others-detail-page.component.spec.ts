import { ComponentRef } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { of } from 'rxjs';

import { Conversation, ProposalDetail, ProposalEventsPage } from '../../models/proposal.model';
import { AssignProposalRequest } from '../../models/proposal-actions.model';
import { PROPOSAL_API_SERVICE } from '../../services/proposal-api.service';
import { ProposalOthersDetailPageComponent } from './proposal-others-detail-page.component';

const ASSIGNEE = {
  permissionId: 'permission-curatorial',
  user: { id: 'staff-2', name: 'Carolina Silva', email: 'carol@example.test' },
  group: 'CURATORIAL' as const,
};

const PROPOSAL: ProposalDetail = {
  id: 'proposal-1',
  referenceNumber: 'VR-2026-002',
  title: 'Manuscript digitisation request',
  status: 'PENDING',
  type: 'IN_SITU_VISIT',
  beginDate: '2026-07-01',
  endDate: '2026-12-31',
  requestedBy: {
    permissionId: 'permission-external',
    user: { id: 'user-1', name: 'Alice Ferreira', email: 'alice@example.test' },
    group: 'EXTERNAL',
  },
  assignedTo: ASSIGNEE,
  collectionUseProject: {
    id: 'project-1',
    referenceNumber: 'CUP-00000123',
    title: 'Manuscript digitisation request',
    status: 'CREATED',
  },
  submittedAt: '2026-05-01T10:00:00',
  conversationId: 'conversation-1',
  documents: [],
  requestedObjects: [],
};

const CONVERSATION: Conversation = {
  conversationId: 'conversation-1',
  proposalId: 'proposal-1',
  messages: [
    {
      id: 'message-1',
      sentAt: '2026-05-01T11:00:00',
      sender: 'alice@example.test',
      recipient: 'collections@example.test',
      subject: 'Initial request',
      body: 'Requesting digitisation of the manuscripts.',
    },
  ],
  page: 0,
  size: 20,
  totalElements: 1,
  totalPages: 1,
};

const EVENTS: ProposalEventsPage = {
  proposalId: 'proposal-1',
  content: [
    { occurredAt: '2026-05-01T10:00:00', type: 'SUBMITTED', triggeredBy: ASSIGNEE, note: null },
    { occurredAt: '2026-05-02T09:30:00', type: 'ASSIGNED', triggeredBy: ASSIGNEE, note: null },
  ],
  page: 0,
  size: 20,
  totalElements: 2,
  totalPages: 1,
};

class ProposalApiServiceStub {
  readonly assignCalls: { proposalId: string; payload: AssignProposalRequest }[] = [];

  getProposal() {
    return of(PROPOSAL);
  }
  getConversation() {
    return of(CONVERSATION);
  }
  listEvents() {
    return of(EVENTS);
  }
  assignProposal(proposalId: string, payload: AssignProposalRequest) {
    this.assignCalls.push({ proposalId, payload });
    return of({ ...PROPOSAL, status: 'PENDING' as const });
  }
}

describe('ProposalOthersDetailPageComponent', () => {
  let proposalService: ProposalApiServiceStub;

  beforeEach(async () => {
    proposalService = new ProposalApiServiceStub();

    await TestBed.configureTestingModule({
      imports: [ProposalOthersDetailPageComponent],
      providers: [provideRouter([]), { provide: PROPOSAL_API_SERVICE, useValue: proposalService }],
    }).compileComponents();
  });

  async function render() {
    const fixture = TestBed.createComponent(ProposalOthersDetailPageComponent);
    const componentRef: ComponentRef<ProposalOthersDetailPageComponent> = fixture.componentRef;
    componentRef.setInput('id', 'proposal-1');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    return fixture;
  }

  it('renders the proposal header and the current assignment', async () => {
    const fixture = await render();
    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';

    expect(text).toContain('VR-2026-002');
    expect(text).toContain('Manuscript digitisation request');
    expect(text).toContain('Current assignment');
    expect(text).toContain('Carolina Silva');
    expect(text).toContain('carol@example.test');
    expect(text).toContain('Curatorial');
  });

  it('shows the conversation as read-only history (no reply composer)', async () => {
    const fixture = await render();
    const compiled = fixture.nativeElement as HTMLElement;

    expect(compiled.textContent).toContain('Requesting digitisation of the manuscripts.');
    expect(compiled.querySelector('.reply-composer')).toBeNull();
  });

  it('confirms taking over then assigns it and redirects to my assignments', async () => {
    const router = TestBed.inject(Router);
    const navigateSpy = vi.spyOn(router, 'navigate').mockResolvedValue(true);

    const fixture = await render();
    const compiled = fixture.nativeElement as HTMLElement;

    buttonByText(compiled, 'Take over').click();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(proposalService.assignCalls).toEqual([]);
    expect(compiled.textContent).toContain('Take over assignment?');
    expect(compiled.textContent).toContain(
      'This will move VR-2026-002 from Carolina Silva to you.',
    );

    compiled.querySelector<HTMLButtonElement>('.confirm-modal__button--primary')!.click();
    fixture.detectChanges();
    await fixture.whenStable();

    expect(proposalService.assignCalls).toEqual([
      { proposalId: 'proposal-1', payload: { note: '' } },
    ]);
    expect(navigateSpy).toHaveBeenCalledWith([
      '/p/collections/proposals/my-assignments',
      'proposal-1',
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
