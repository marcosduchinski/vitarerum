import { ComponentRef, signal, WritableSignal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { of } from 'rxjs';

import { IDENTITY_SERVICE } from '@core/auth/identity.service';
import { UserDetail } from '@core/auth/models/user.model';
import { USER_MANAGEMENT_SERVICE } from '@features/admin/services/user-management.service';
import { Page } from '@shared/models/page.model';

import { Conversation, ProposalDetail, ProposalEventsPage } from '../../models/proposal.model';
import { PROPOSAL_API_SERVICE } from '../../services/proposal-api.service';
import { ProposalDetailPageComponent } from './proposal-detail-page.component';

const PROPOSAL: ProposalDetail = {
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
      recipient: 'Collections management',
      subject: 'Initial collection use request',
      body: '<p>Please review this research request.</p>',
    },
    {
      id: 'message-2',
      sentAt: '2026-05-01T14:00:00',
      sender: 'carol@example.test',
      recipient: 'alice@example.test',
      subject: 'Requested file response',
      body: '<p>Attached signed response for museum review.</p>',
      attachments: [
        {
          documentId: 'document-1',
          fileName: 'signed-response.docx',
        },
      ],
    },
  ],
  page: 0,
  size: 20,
  totalElements: 2,
  totalPages: 0,
};

const EVENTS: ProposalEventsPage = {
  proposalId: 'proposal-1',
  content: [],
  page: 0,
  size: 20,
  totalElements: 0,
  totalPages: 0,
};

const STAFF_USERS: Page<UserDetail> = {
  content: [
    {
      id: 'staff-2',
      name: 'Carolina Silva',
      email: 'carol@example.test',
      permissions: [
        {
          permissionId: 'permission-curatorial',
          group: { id: 'group-curatorial', name: 'CURATORIAL' },
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
  readonly assignCalls: {
    readonly proposalId: string;
    readonly payload: { readonly note: string };
  }[] = [];
  readonly forwardCalls: {
    readonly proposalId: string;
    readonly payload: { readonly targetPermissionId: string; readonly note: string };
  }[] = [];
  proposalLoads = 0;
  eventLoads = 0;

  getProposal() {
    this.proposalLoads += 1;
    return of(PROPOSAL);
  }

  getConversation() {
    return of(CONVERSATION);
  }

  listEvents() {
    this.eventLoads += 1;
    return of(EVENTS);
  }

  assignProposal(proposalId: string, payload: { readonly note: string }) {
    this.assignCalls.push({ proposalId, payload });
    return of({ id: proposalId, status: 'PENDING', assignedTo: null, lastEvent: null });
  }

  forwardProposal(
    proposalId: string,
    payload: { readonly targetPermissionId: string; readonly note: string },
  ) {
    this.forwardCalls.push({ proposalId, payload });
    return of({ id: proposalId, status: 'SUBMITTED', assignedTo: null, lastEvent: null });
  }
}

class UserManagementServiceStub {
  listUsers() {
    return of(STAFF_USERS);
  }
}

describe('ProposalDetailPageComponent', () => {
  let proposalService: ProposalApiServiceStub;
  let identityIsStaff: WritableSignal<boolean>;

  beforeEach(async () => {
    proposalService = new ProposalApiServiceStub();
    // Default to a staff viewer; the external-viewer test flips this to false.
    identityIsStaff = signal(true);

    await TestBed.configureTestingModule({
      imports: [ProposalDetailPageComponent],
      providers: [
        provideRouter([]),
        { provide: PROPOSAL_API_SERVICE, useValue: proposalService },
        { provide: USER_MANAGEMENT_SERVICE, useClass: UserManagementServiceStub },
        { provide: IDENTITY_SERVICE, useValue: { isStaff: identityIsStaff.asReadonly() } },
      ],
    }).compileComponents();
  });

  it('renders conversation messages with roles, icons, rich bodies, and attachments', async () => {
    const fixture = TestBed.createComponent(ProposalDetailPageComponent);
    const componentRef: ComponentRef<ProposalDetailPageComponent> = fixture.componentRef;

    componentRef.setInput('id', 'proposal-1');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    const messages = Array.from(compiled.querySelectorAll<HTMLElement>('.message'));

    expect(messages).toHaveLength(2);
    expect(messages[0].classList).toContain('message--requester');
    expect(messages[0].querySelector('.message__avatar .pi-user')).not.toBeNull();
    expect(messages[0].querySelector('.message__content')).not.toBeNull();
    expect(messages[0].textContent).toContain('Requester');
    expect(messages[0].querySelector('.message__body p')?.textContent).toContain(
      'Please review this research request.',
    );

    expect(messages[1].classList).not.toContain('message--requester');
    expect(messages[1].querySelector('.message__avatar .pi-briefcase')).not.toBeNull();
    expect(messages[1].textContent).toContain('Staff');
    expect(messages[1].textContent).toContain('signed-response.docx');
    expect(messages[1].querySelector('.message-attachments .pi-paperclip')).not.toBeNull();
  });

  it('hides the decision desk (assume/forward) from external viewers', async () => {
    identityIsStaff.set(false);

    const fixture = TestBed.createComponent(ProposalDetailPageComponent);
    const componentRef: ComponentRef<ProposalDetailPageComponent> = fixture.componentRef;

    componentRef.setInput('id', 'proposal-1');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;

    expect(compiled.textContent).not.toContain('Decision desk');
    expect(
      Array.from(compiled.querySelectorAll<HTMLButtonElement>('button')).some(
        (button) => button.textContent?.trim() === 'Assign to me',
      ),
    ).toBe(false);
    expect(compiled.textContent).toContain('No routing action is available for this status.');
  });

  it('confirms assuming a submitted proposal then redirects to the assignment detail', async () => {
    const router = TestBed.inject(Router);
    const navigateSpy = vi.spyOn(router, 'navigate').mockResolvedValue(true);

    const fixture = TestBed.createComponent(ProposalDetailPageComponent);
    const componentRef: ComponentRef<ProposalDetailPageComponent> = fixture.componentRef;

    componentRef.setInput('id', 'proposal-1');
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
    await new Promise<void>((resolve) => setTimeout(resolve));
    fixture.detectChanges();

    expect(proposalService.assignCalls).toEqual([
      {
        proposalId: 'proposal-1',
        payload: { note: 'Assigned to self from proposal detail.' },
      },
    ]);
    expect(navigateSpy).toHaveBeenCalledWith([
      '/p/collections/proposals/my-assignments',
      'proposal-1',
    ]);
  });

  it('opens the forward modal and forwards after confirmation', async () => {
    const fixture = TestBed.createComponent(ProposalDetailPageComponent);
    const componentRef: ComponentRef<ProposalDetailPageComponent> = fixture.componentRef;

    componentRef.setInput('id', 'proposal-1');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;

    buttonByText(compiled, 'Forward').click();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const dialog = compiled.querySelector<HTMLElement>('[role="dialog"]');
    const select = compiled.querySelector<HTMLSelectElement>('#forward-modal-target');
    const note = compiled.querySelector<HTMLTextAreaElement>('#forward-modal-note');
    const submit = Array.from(dialog?.querySelectorAll<HTMLButtonElement>('button') ?? []).find(
      (button) => button.textContent?.trim() === 'Forward',
    );

    expect(compiled.querySelector('.forward-panel')).toBeNull();
    expect(dialog).not.toBeNull();
    expect(dialog!.textContent).toContain('VR-2026-001');
    expect(select).not.toBeNull();
    expect(note).not.toBeNull();
    expect(submit).not.toBeNull();
    expect(submit!.disabled).toBe(true);

    select!.value = 'permission-curatorial';
    select!.dispatchEvent(new Event('change'));
    note!.value = 'Please review curatorial routing.';
    note!.dispatchEvent(new Event('input'));
    fixture.detectChanges();

    expect(submit!.disabled).toBe(false);

    submit!.click();
    fixture.detectChanges();
    await fixture.whenStable();
    await new Promise<void>((resolve) => setTimeout(resolve));
    fixture.detectChanges();

    expect(proposalService.forwardCalls).toEqual([
      {
        proposalId: 'proposal-1',
        payload: {
          targetPermissionId: 'permission-curatorial',
          note: 'Please review curatorial routing.',
        },
      },
    ]);
    expect(proposalService.proposalLoads).toBeGreaterThan(1);
    expect(proposalService.eventLoads).toBeGreaterThan(1);
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
