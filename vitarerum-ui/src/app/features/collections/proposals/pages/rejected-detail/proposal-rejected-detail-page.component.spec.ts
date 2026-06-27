import { ComponentRef } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of } from 'rxjs';

import { Conversation, ProposalDetail, ProposalEventsPage } from '../../models/proposal.model';
import { PROPOSAL_API_SERVICE } from '../../services/proposal-api.service';
import { ProposalRejectedDetailPageComponent } from './proposal-rejected-detail-page.component';

const STAFF = {
  permissionId: 'permission-staff',
  user: { id: 'staff-1', name: 'Bob Santos', email: 'bob@example.test' },
  group: 'COLLECTIONS_MANAGEMENT' as const,
};

const PROPOSAL: ProposalDetail = {
  id: 'proposal-1',
  referenceNumber: 'VR-2026-009',
  title: 'Out-of-scope reproduction request',
  status: 'REJECTED',
  type: 'IN_SITU_VISIT',
  beginDate: '2026-07-01',
  endDate: '2026-12-31',
  requestedBy: {
    permissionId: 'permission-external',
    user: { id: 'user-1', name: 'Alice Ferreira', email: 'alice@example.test' },
    group: 'EXTERNAL',
  },
  assignedTo: STAFF,
  collectionUseProject: {
    id: 'project-1',
    referenceNumber: 'CUP-00000123',
    title: 'Out-of-scope reproduction request',
    status: 'CANCELLED',
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
      body: 'Requesting reproduction of restricted material.',
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
    { occurredAt: '2026-05-01T10:00:00', type: 'SUBMITTED', triggeredBy: STAFF, note: null },
    {
      occurredAt: '2026-06-03T14:00:00',
      type: 'REJECTED',
      triggeredBy: STAFF,
      note: 'Outside the permitted use of the collection.',
    },
  ],
  page: 0,
  size: 20,
  totalElements: 2,
  totalPages: 1,
};

class ProposalApiServiceStub {
  getProposal() {
    return of(PROPOSAL);
  }
  getConversation() {
    return of(CONVERSATION);
  }
  listEvents() {
    return of(EVENTS);
  }
}

describe('ProposalRejectedDetailPageComponent', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ProposalRejectedDetailPageComponent],
      providers: [
        provideRouter([]),
        { provide: PROPOSAL_API_SERVICE, useClass: ProposalApiServiceStub },
      ],
    }).compileComponents();
  });

  async function render() {
    const fixture = TestBed.createComponent(ProposalRejectedDetailPageComponent);
    const componentRef: ComponentRef<ProposalRejectedDetailPageComponent> = fixture.componentRef;
    componentRef.setInput('id', 'proposal-1');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  it('renders the proposal header and the rejection details', async () => {
    const compiled = await render();
    const text = compiled.textContent ?? '';

    expect(text).toContain('VR-2026-009');
    expect(text).toContain('Out-of-scope reproduction request');
    expect(text).toContain('Rejected');

    expect(text).toContain('Rejection');
    expect(text).toContain('Rejected by');
    expect(text).toContain('Bob Santos');
    expect(text).toContain('03 Jun 2026');
    expect(text).toContain('Outside the permitted use of the collection.');
  });

  it('shows the conversation as read-only history (no reply composer)', async () => {
    const compiled = await render();

    expect(compiled.textContent).toContain('Requesting reproduction of restricted material.');
    expect(compiled.querySelector('.reply-composer')).toBeNull();
  });
});
