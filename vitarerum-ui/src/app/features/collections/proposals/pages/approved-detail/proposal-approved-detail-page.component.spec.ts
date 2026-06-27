import { ComponentRef } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of } from 'rxjs';

import { Conversation, ProposalDetail, ProposalEventsPage } from '../../models/proposal.model';
import { PROPOSAL_API_SERVICE } from '../../services/proposal-api.service';
import { ProposalApprovedDetailPageComponent } from './proposal-approved-detail-page.component';

const STAFF = {
  permissionId: 'permission-staff',
  user: { id: 'staff-1', name: 'Bob Santos', email: 'bob@example.test' },
  group: 'COLLECTIONS_MANAGEMENT' as const,
};

const PROPOSAL: ProposalDetail = {
  id: 'proposal-1',
  referenceNumber: 'VR-2026-001',
  title: 'Photographic history of Rio de Janeiro port, 1890-1930',
  status: 'APPROVED',
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
    title: 'Photographic history of Rio de Janeiro port, 1890-1930',
    status: 'IN_PROGRESS',
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
      body: 'Requesting access to the port photographs.',
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
    { occurredAt: '2026-06-02T09:30:00', type: 'APPROVED', triggeredBy: STAFF, note: null },
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

describe('ProposalApprovedDetailPageComponent', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ProposalApprovedDetailPageComponent],
      providers: [
        provideRouter([]),
        { provide: PROPOSAL_API_SERVICE, useClass: ProposalApiServiceStub },
      ],
    }).compileComponents();
  });

  async function render() {
    const fixture = TestBed.createComponent(ProposalApprovedDetailPageComponent);
    const componentRef: ComponentRef<ProposalApprovedDetailPageComponent> = fixture.componentRef;
    componentRef.setInput('id', 'proposal-1');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  it('renders the proposal header and the resulting project card', async () => {
    const compiled = await render();
    const text = compiled.textContent ?? '';

    expect(text).toContain('VR-2026-001');
    expect(text).toContain('Photographic history of Rio de Janeiro port, 1890-1930');
    expect(text).toContain('Approved');

    expect(text).toContain('Resulting project');
    expect(text).toContain('CUP-00000123');
    expect(text).toContain('In progress');
    expect(text).toContain('01 Jul 2026');
    expect(text).toContain('31 Dec 2026');
  });

  it('surfaces who approved it and when from the event log', async () => {
    const compiled = await render();
    const text = compiled.textContent ?? '';

    expect(text).toContain('Approved by');
    expect(text).toContain('Bob Santos');
    expect(text).toContain('02 Jun 2026');
  });

  it('links to the resulting project', async () => {
    const compiled = await render();
    const cta = Array.from(compiled.querySelectorAll<HTMLAnchorElement>('a')).find((a) =>
      a.textContent?.includes('Go to project'),
    );

    expect(cta).not.toBeUndefined();
    expect(cta!.getAttribute('href')).toContain('/p/collections/projects/project-1');
  });

  it('shows the conversation as read-only history (no reply composer)', async () => {
    const compiled = await render();

    expect(compiled.textContent).toContain('Requesting access to the port photographs.');
    expect(compiled.querySelector('.reply-composer')).toBeNull();
  });
});
