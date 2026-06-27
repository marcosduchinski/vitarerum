import { ComponentRef } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';
import { provideRouter, Router } from '@angular/router';
import { of } from 'rxjs';

import { UserDetail } from '@core/auth/models/user.model';
import { PROPOSAL_CHAT_SERVICE } from '@features/proposal-chat/services/proposal-chat.service';
import { ProposalChatPanelComponent } from '@features/proposal-chat/components/proposal-chat-panel/proposal-chat-panel.component';
import { USER_MANAGEMENT_SERVICE } from '@features/admin/services/user-management.service';
import { Page } from '@shared/models/page.model';
import {
  IntendedUseSuggestion,
  ProposalChatContext,
  ProposalChatContextQuery,
  SuggestIntendedUseRequest,
} from '@features/proposal-chat/models/proposal-chat.model';

import {
  Conversation,
  Document,
  Message,
  ProposalDetail,
  ProposalEventsPage,
  SendMessageRequest,
} from '../../models/proposal.model';
import { PROPOSAL_API_SERVICE } from '../../services/proposal-api.service';
import { ApproveProposalRequest, UpdateProposalRequest } from '../../models/proposal-actions.model';
import { ProposalMyDetailPageComponent } from './proposal-my-detail-page.component';

const wait = (ms: number): Promise<void> => new Promise((resolve) => setTimeout(resolve, ms));

const PROPOSAL: ProposalDetail = {
  id: 'proposal-1',
  referenceNumber: 'VR-2026-001',
  title: 'Photographic history of Rio de Janeiro port, 1890-1930',
  status: 'PENDING',
  type: 'IN_SITU_VISIT',
  intendedUse: {
    useType: 'IN_SITU_VISIT',
    description: 'Research visit to consult photographic records on site.',
  },
  beginDate: '2026-07-01',
  endDate: '2026-12-31',
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
      subject: 'Initial request',
      body: 'Please review this research request.',
    },
    {
      id: 'message-2',
      sentAt: '2026-05-01T14:00:00',
      sender: 'bob@example.test',
      recipient: 'alice@example.test',
      subject: 'Response to VR-2026-001',
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
  totalPages: 1,
};

const EVENTS: ProposalEventsPage = {
  proposalId: 'proposal-1',
  content: [
    {
      occurredAt: '2026-05-01T10:00:00',
      type: 'SUBMITTED',
      triggeredBy: PROPOSAL.requestedBy,
      note: 'Submitted for review.',
    },
  ],
  page: 0,
  size: 20,
  totalElements: 1,
  totalPages: 1,
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
    {
      id: 'staff-3',
      name: 'Dan Oliveira',
      email: 'dan@example.test',
      permissions: [
        {
          permissionId: 'permission-direction',
          group: { id: 'group-direction', name: 'DIRECTION' },
        },
      ],
    },
  ],
  page: 0,
  size: 100,
  totalElements: 2,
  totalPages: 1,
};

class ProposalApiServiceStub {
  readonly getProposalCalls: string[] = [];
  readonly listEventsCalls: string[] = [];
  readonly updateProposalCalls: {
    readonly proposalId: string;
    readonly request: UpdateProposalRequest;
  }[] = [];
  readonly approveCalls: {
    readonly proposalId: string;
    readonly payload: ApproveProposalRequest;
  }[] = [];
  readonly rejectCalls: {
    readonly proposalId: string;
    readonly payload: { readonly reason: string };
  }[] = [];
  readonly uploadCalls: {
    readonly proposalId: string;
    readonly file: File;
    readonly documentType: string;
  }[] = [];
  readonly sendMessageCalls: {
    readonly proposalId: string;
    readonly payload: SendMessageRequest;
  }[] = [];
  private nextDocumentId = 1;
  private proposal = PROPOSAL;

  setProposal(proposal: ProposalDetail): void {
    this.proposal = proposal;
  }

  getProposal(proposalId: string) {
    this.getProposalCalls.push(proposalId);
    return of(this.proposal);
  }

  getConversation() {
    return of(CONVERSATION);
  }

  listEvents(proposalId: string) {
    this.listEventsCalls.push(proposalId);
    return of(EVENTS);
  }

  updateProposal(proposalId: string, request: UpdateProposalRequest) {
    this.updateProposalCalls.push({ proposalId, request });
    this.proposal = {
      ...this.proposal,
      type: request.intendedUse?.useType ?? this.proposal.type,
      intendedUse: request.intendedUse ?? this.proposal.intendedUse,
    };
    return of({
      id: proposalId,
      referenceNumber: this.proposal.referenceNumber,
      title: this.proposal.title,
      status: this.proposal.status,
      beginDate: this.proposal.beginDate ?? null,
      endDate: this.proposal.endDate ?? null,
      lastEvent: null,
    });
  }

  uploadDocument(proposalId: string, file: File, documentType: string) {
    const document: Document = {
      id: `uploaded-document-${this.nextDocumentId++}`,
      type: documentType,
      fileName: file.name,
      fileReference: `mock-file-reference/${file.name}`,
      submittedAt: '2026-05-02T10:00:00',
      submittedBy: PROPOSAL.assignedTo ?? PROPOSAL.requestedBy,
    };

    this.uploadCalls.push({ proposalId, file, documentType });
    return of(document);
  }

  sendMessage(proposalId: string, payload: SendMessageRequest) {
    const message: Message = {
      id: 'sent-message-1',
      sentAt: '2026-05-02T10:05:00',
      sender: PROPOSAL.assignedTo?.user.email ?? '',
      recipient: payload.recipient,
      subject: payload.subject,
      body: payload.body,
      attachments: payload.documentIds?.map((documentId) => ({
        documentId,
        fileName: 'signed-response.docx',
      })),
    };

    this.sendMessageCalls.push({ proposalId, payload });
    return of(message);
  }

  approveProposal(proposalId: string, payload: ApproveProposalRequest) {
    this.approveCalls.push({ proposalId, payload });
    return of({
      proposal: {
        id: proposalId,
        status: 'APPROVED' as const,
        lastEvent: EVENTS.content[0],
      },
      collectionUseProject: {
        ...PROPOSAL.collectionUseProject!,
        status: 'CREATED' as const,
      },
    });
  }

  rejectProposal(proposalId: string, payload: { readonly reason: string }) {
    this.rejectCalls.push({ proposalId, payload });
    return of({
      proposal: {
        id: proposalId,
        status: 'REJECTED' as const,
        lastEvent: EVENTS.content[0],
      },
      collectionUseProject: {
        ...PROPOSAL.collectionUseProject!,
        status: 'CANCELLED' as const,
      },
    });
  }
}

class UserManagementServiceStub {
  listUsers() {
    return of(STAFF_USERS);
  }
}

function makeProposalChatContext(messageId: string): ProposalChatContext {
  const message =
    CONVERSATION.messages.find((item) => item.id === messageId) ?? CONVERSATION.messages[0];
  return {
    conversationId: PROPOSAL.conversationId,
    focusMessage: {
      messageId: message.id,
      sentAt: message.sentAt,
      sender: message.sender,
      subject: message.subject,
      body: message.body,
    },
    proposal: {
      proposalId: PROPOSAL.id,
      referenceNumber: PROPOSAL.referenceNumber,
      title: PROPOSAL.title,
      status: PROPOSAL.status,
      intendedUse: PROPOSAL.intendedUse!,
    },
  };
}

class ProposalChatServiceStub {
  readonly contextCalls: ProposalChatContextQuery[] = [];
  readonly suggestionCalls: SuggestIntendedUseRequest[] = [];

  getContext(query: ProposalChatContextQuery) {
    this.contextCalls.push(query);
    return of(makeProposalChatContext(query.messageId));
  }

  suggestIntendedUse(request: SuggestIntendedUseRequest) {
    this.suggestionCalls.push(request);
    const suggestion: IntendedUseSuggestion = {
      intendedUse: {
        useType: 'IN_SITU_VISIT',
        description: 'Research access to photographic records.',
      },
      confidence: 0.82,
      rationale: 'The selected message mentions a research request.',
      source: request,
    };
    return of(suggestion);
  }
}

async function selectPanel(
  fixture: ComponentFixture<ProposalMyDetailPageComponent>,
  name: 'Overview' | 'Conversation' | 'AI Assistance' | 'Actions',
): Promise<void> {
  const compiled = fixture.nativeElement as HTMLElement;
  const tab = Array.from(compiled.querySelectorAll<HTMLButtonElement>('[role="tab"]')).find(
    (button) => button.textContent?.trim() === name,
  );

  expect(tab).not.toBeNull();

  tab!.click();
  fixture.detectChanges();
  await fixture.whenStable();
  fixture.detectChanges();
}

describe('ProposalMyDetailPageComponent', () => {
  let proposalService: ProposalApiServiceStub;
  let proposalChatService: ProposalChatServiceStub;

  beforeEach(async () => {
    proposalService = new ProposalApiServiceStub();
    proposalChatService = new ProposalChatServiceStub();

    await TestBed.configureTestingModule({
      imports: [ProposalMyDetailPageComponent],
      providers: [
        provideRouter([]),
        { provide: PROPOSAL_API_SERVICE, useValue: proposalService },
        { provide: USER_MANAGEMENT_SERVICE, useClass: UserManagementServiceStub },
        { provide: PROPOSAL_CHAT_SERVICE, useValue: proposalChatService },
      ],
    }).compileComponents();
  });

  it('renders the assignment detail context from the proposal workflow', async () => {
    const fixture = TestBed.createComponent(ProposalMyDetailPageComponent);
    const componentRef: ComponentRef<ProposalMyDetailPageComponent> = fixture.componentRef;

    componentRef.setInput('id', 'proposal-1');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;

    expect(compiled.textContent).toContain('Back to my assignments');
    expect(
      compiled.querySelector('a[href="/p/collections/proposals/my-assignments"]'),
    ).not.toBeNull();
    expect(compiled.textContent).toContain('VR-2026-001');
    expect(compiled.textContent).toContain('Photographic history of Rio de Janeiro port');
    expect(compiled.textContent).toContain('Under review');
    expect(compiled.textContent).toContain('Requested by');
    expect(compiled.textContent).toContain('Alice Ferreira');
    expect(compiled.textContent).toContain('Assigned to');
    expect(compiled.textContent).toContain('Bob Santos');
    expect(compiled.textContent).toContain('Conversation');
    expect(compiled.textContent).toContain('AI Assistance');
    expect(compiled.textContent).toContain('Event log');
    expect(compiled.textContent).toContain('SUBMITTED');
    // The decision actions now live behind the Actions tab, not the header.
    expect(compiled.textContent).toContain('Actions');
    expect(
      Array.from(compiled.querySelectorAll<HTMLButtonElement>('button')).some((button) => {
        const label = button.textContent?.trim();
        return label === 'Accept' || label === 'Reject' || label === 'Edit';
      }),
    ).toBe(false);
    expect(compiled.querySelector('#actions-panel')).toBeNull();
    expect(compiled.querySelector('[role="tab"][aria-selected="true"]')?.textContent).toContain(
      'Overview',
    );
    expect(compiled.querySelector('#overview-panel')).not.toBeNull();
    expect(compiled.querySelector('#conversation-panel')).toBeNull();
    expect(compiled.querySelector('#ai-assistance-panel')).toBeNull();
    expect(compiled.textContent).not.toContain('Initial request');
  });

  it('navigates from the Decision Desk to the proposal edit page', async () => {
    const router = TestBed.inject(Router);
    const navigate = vi.spyOn(router, 'navigate').mockResolvedValue(true);
    const fixture = TestBed.createComponent(ProposalMyDetailPageComponent);
    fixture.componentRef.setInput('id', 'proposal-1');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    await selectPanel(fixture, 'Actions');

    const compiled = fixture.nativeElement as HTMLElement;
    const editButton = Array.from(compiled.querySelectorAll<HTMLButtonElement>('button')).find(
      (button) => button.textContent?.trim() === 'Edit',
    );

    expect(editButton).toBeDefined();
    editButton!.click();
    expect(navigate).toHaveBeenCalledWith([
      '/p/collections/proposals/my-assignments',
      'proposal-1',
      'edit',
    ]);
  });

  it('simulates creating a temporary external user without calling the backend', async () => {
    const fixture = TestBed.createComponent(ProposalMyDetailPageComponent);
    fixture.componentRef.setInput('id', 'proposal-1');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    await selectPanel(fixture, 'Actions');

    const compiled = fixture.nativeElement as HTMLElement;
    const text = compiled.textContent?.replace(/\s+/g, ' ') ?? '';
    const createButton = Array.from(compiled.querySelectorAll<HTMLButtonElement>('button')).find(
      (button) => button.textContent?.trim() === 'Create user',
    );

    expect(text).toContain('Create temporary external user');
    expect(text).toContain(
      'Create a temporary external account for the requester if no external user exists for their email address.',
    );
    expect(createButton).toBeDefined();
    expect(createButton!.disabled).toBe(false);

    createButton!.click();
    fixture.detectChanges();

    const feedback = compiled.querySelector<HTMLElement>('app-feedback-message [role="status"]');
    expect(feedback?.textContent).toContain('Temporary external user created');
    expect(feedback?.textContent).toContain(
      'A new temporary external user for alice@example.test was created.',
    );
    expect(createButton!.disabled).toBe(true);
    expect(createButton!.textContent?.trim()).toBe('Created');
    expect(proposalService.updateProposalCalls).toEqual([]);
    expect(proposalService.approveCalls).toEqual([]);
    expect(proposalService.rejectCalls).toEqual([]);
    expect(proposalService.uploadCalls).toEqual([]);
    expect(proposalService.sendMessageCalls).toEqual([]);
  });

  it('hides the Edit action when the proposal has a terminal status', async () => {
    proposalService.setProposal({ ...PROPOSAL, status: 'APPROVED' });
    const fixture = TestBed.createComponent(ProposalMyDetailPageComponent);
    fixture.componentRef.setInput('id', 'proposal-1');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    await selectPanel(fixture, 'Actions');

    const compiled = fixture.nativeElement as HTMLElement;

    expect(
      Array.from(compiled.querySelectorAll<HTMLButtonElement>('button')).some(
        (button) => button.textContent?.trim() === 'Edit',
      ),
    ).toBe(false);
    expect(compiled.textContent).not.toContain('Create temporary external user');
    expect(compiled.textContent).toContain('No actions available for this status.');
  });

  it('uses an accessible fallback when the proposal title is cleared', async () => {
    proposalService.setProposal({ ...PROPOSAL, title: null } as unknown as ProposalDetail);
    const fixture = TestBed.createComponent(ProposalMyDetailPageComponent);
    fixture.componentRef.setInput('id', 'proposal-1');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const heading = (fixture.nativeElement as HTMLElement).querySelector<HTMLHeadingElement>('h1');

    expect(heading?.textContent?.trim()).toBe('Untitled proposal');
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('VR-2026-001');
  });

  it('switches between overview and conversation panels', async () => {
    const fixture = TestBed.createComponent(ProposalMyDetailPageComponent);
    const componentRef: ComponentRef<ProposalMyDetailPageComponent> = fixture.componentRef;

    componentRef.setInput('id', 'proposal-1');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    await selectPanel(fixture, 'Conversation');

    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelector('[role="tab"][aria-selected="true"]')?.textContent).toContain(
      'Conversation',
    );
    expect(compiled.querySelector('#conversation-panel')).not.toBeNull();
    expect(compiled.textContent).toContain('Initial request');
    expect(compiled.textContent).toContain('signed-response.docx');
  });

  it('enables the staff-only requested-object disclosure in the conversation panel', async () => {
    proposalService.setProposal({
      ...PROPOSAL,
      requestedObjects: [
        {
          id: 'requested-object-1',
          objectReference: {
            inventoryNumber: 'MNHN-2026-001',
            displayTitle: 'Iberian lynx specimen',
            objectName: 'Lynx pardinus',
            briefDescriptionSnapshot: 'Adult study skin',
          },
          category: 'Zoology',
          description: 'Requested for comparative research',
          requestedAt: '2026-05-01T10:00:00',
          requestedBy: PROPOSAL.requestedBy,
        },
      ],
    });
    const fixture = TestBed.createComponent(ProposalMyDetailPageComponent);
    fixture.componentRef.setInput('id', 'proposal-1');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    await selectPanel(fixture, 'Conversation');

    const toggle = (fixture.nativeElement as HTMLElement).querySelector<HTMLButtonElement>(
      '[aria-controls="requested-object-picker-panel"]',
    );
    expect(toggle).not.toBeNull();
    expect(toggle?.getAttribute('aria-expanded')).toBe('false');
  });

  it('shows an empty AI Assistance panel until a message is selected', async () => {
    const fixture = TestBed.createComponent(ProposalMyDetailPageComponent);
    const componentRef: ComponentRef<ProposalMyDetailPageComponent> = fixture.componentRef;

    componentRef.setInput('id', 'proposal-1');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    await selectPanel(fixture, 'AI Assistance');

    const compiled = fixture.nativeElement as HTMLElement;

    expect(compiled.querySelector('[role="tab"][aria-selected="true"]')?.textContent).toContain(
      'AI Assistance',
    );
    expect(compiled.querySelector('#ai-assistance-panel')).not.toBeNull();
    expect(compiled.textContent).toContain(
      'Select a message from the Conversation tab to run intended-use triage.',
    );
    expect(proposalChatService.contextCalls).toEqual([]);
  });

  it('marks requester and staff messages with distinct roles and icons', async () => {
    const fixture = TestBed.createComponent(ProposalMyDetailPageComponent);
    const componentRef: ComponentRef<ProposalMyDetailPageComponent> = fixture.componentRef;

    componentRef.setInput('id', 'proposal-1');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    await selectPanel(fixture, 'Conversation');

    const compiled = fixture.nativeElement as HTMLElement;
    const messages = Array.from(compiled.querySelectorAll<HTMLElement>('.message'));

    expect(messages).toHaveLength(2);
    expect(messages[0].textContent).toContain('Requester');
    expect(messages[0].querySelector('.pi-user')).not.toBeNull();
    expect(messages[1].textContent).toContain('COLLECTIONS MANAGEMENT');
    expect(messages[1].querySelector('.pi-briefcase')).not.toBeNull();
    expect(messages[1].textContent).toContain('signed-response.docx');
  });

  it('opens ProposalChat triage for the selected conversation message', async () => {
    const fixture = TestBed.createComponent(ProposalMyDetailPageComponent);
    const componentRef: ComponentRef<ProposalMyDetailPageComponent> = fixture.componentRef;

    componentRef.setInput('id', 'proposal-1');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    await selectPanel(fixture, 'Conversation');

    const compiled = fixture.nativeElement as HTMLElement;
    const buttons = Array.from(
      compiled.querySelectorAll<HTMLButtonElement>('[aria-label^="Run intended-use triage"]'),
    );

    expect(buttons).toHaveLength(2);

    buttons[0].click();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(compiled.querySelector('[role="tab"][aria-selected="true"]')?.textContent).toContain(
      'AI Assistance',
    );
    expect(compiled.querySelector('#ai-assistance-panel')).not.toBeNull();
    expect(proposalChatService.contextCalls).toEqual([
      { conversationId: 'conversation-1', messageId: 'message-1' },
    ]);
    expect(compiled.textContent).toContain('ProposalChat');
    expect(compiled.textContent).toContain('Initial request');
    expect(compiled.textContent).toContain('Requester message');
    expect(compiled.querySelector('[data-task="intended-use"]')).not.toBeNull();
    expect(proposalChatService.suggestionCalls).toEqual([]);
  });

  it('applies triage suggestions and returns to the overview panel', async () => {
    const fixture = TestBed.createComponent(ProposalMyDetailPageComponent);
    const componentRef: ComponentRef<ProposalMyDetailPageComponent> = fixture.componentRef;

    componentRef.setInput('id', 'proposal-1');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    await selectPanel(fixture, 'Conversation');

    let compiled = fixture.nativeElement as HTMLElement;
    compiled.querySelector<HTMLButtonElement>('[aria-label^="Run intended-use triage"]')!.click();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    compiled = fixture.nativeElement as HTMLElement;
    // Delegate the intended-use task, wait out the assistant's "thinking" pause.
    compiled.querySelector<HTMLButtonElement>('[data-task="intended-use"]')!.click();
    await wait(700);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    (fixture.nativeElement as HTMLElement)
      .querySelector<HTMLButtonElement>('.agent-apply')!
      .click();
    fixture.detectChanges();
    await fixture.whenStable();
    await wait(20);
    fixture.detectChanges();

    expect(proposalService.updateProposalCalls).toEqual([
      {
        proposalId: 'proposal-1',
        request: {
          intendedUse: {
            useType: 'IN_SITU_VISIT',
            description: 'Research access to photographic records.',
          },
        },
      },
    ]);
    expect(
      (fixture.nativeElement as HTMLElement).querySelector('[role="tab"][aria-selected="true"]')
        ?.textContent,
    ).toContain('Overview');
    expect(proposalService.getProposalCalls.length).toBeGreaterThan(1);
    expect(proposalService.listEventsCalls.length).toBeGreaterThan(1);
  });

  it('reloads proposal data after requested objects are added and keeps AI Assistance open', async () => {
    const fixture = TestBed.createComponent(ProposalMyDetailPageComponent);
    fixture.componentRef.setInput('id', 'proposal-1');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    await selectPanel(fixture, 'Conversation');

    (fixture.nativeElement as HTMLElement)
      .querySelector<HTMLButtonElement>('[aria-label^="Run intended-use triage"]')!
      .click();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const proposalCallsBefore = proposalService.getProposalCalls.length;
    const eventCallsBefore = proposalService.listEventsCalls.length;
    const chat = fixture.debugElement.query(By.directive(ProposalChatPanelComponent))
      .componentInstance as ProposalChatPanelComponent;
    chat.requestedObjectsAdded.emit();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(proposalService.getProposalCalls.length).toBeGreaterThan(proposalCallsBefore);
    expect(proposalService.listEventsCalls).toHaveLength(eventCallsBefore);
    expect(
      (fixture.nativeElement as HTMLElement).querySelector('[role="tab"][aria-selected="true"]')
        ?.textContent,
    ).toContain('AI Assistance');
  });

  it('uploads selected files and attaches them to a staff response message', async () => {
    const fixture = TestBed.createComponent(ProposalMyDetailPageComponent);
    const componentRef: ComponentRef<ProposalMyDetailPageComponent> = fixture.componentRef;

    componentRef.setInput('id', 'proposal-1');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    await selectPanel(fixture, 'Conversation');

    const compiled = fixture.nativeElement as HTMLElement;
    const editor = compiled.querySelector<HTMLElement>('.reply-editor');
    const fileInput = compiled.querySelector<HTMLInputElement>('#staff-response-files');
    const sendButton = Array.from(compiled.querySelectorAll<HTMLButtonElement>('button')).find(
      (button) => button.textContent?.includes('Send response'),
    );

    expect(editor).not.toBeNull();
    expect(fileInput).not.toBeNull();
    expect(sendButton).not.toBeNull();

    editor!.innerHTML = '<p>Please review the attached signed files.</p>';
    editor!.dispatchEvent(new Event('input'));

    const file = new File(['signed'], 'signed-response.docx', {
      type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    });
    Object.defineProperty(fileInput!, 'files', {
      value: [file],
      configurable: true,
    });
    fileInput!.dispatchEvent(new Event('change'));

    fixture.detectChanges();

    expect(compiled.textContent).toContain('signed-response.docx');

    sendButton!.click();
    fixture.detectChanges();
    await fixture.whenStable();

    expect(proposalService.uploadCalls).toEqual([
      {
        proposalId: 'proposal-1',
        file,
        documentType: 'STAFF_RESPONSE_ATTACHMENT',
      },
    ]);
    expect(proposalService.sendMessageCalls).toEqual([
      {
        proposalId: 'proposal-1',
        payload: {
          recipient: 'alice@example.test',
          subject: 'Response to VR-2026-001',
          body: '<p>Please review the attached signed files.</p>',
          documentIds: ['uploaded-document-1'],
        },
      },
    ]);
  });

  it('confirms accepting the assignment and navigates to the approved list', async () => {
    const fixture = TestBed.createComponent(ProposalMyDetailPageComponent);
    const componentRef: ComponentRef<ProposalMyDetailPageComponent> = fixture.componentRef;

    componentRef.setInput('id', 'proposal-1');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    await selectPanel(fixture, 'Actions');

    const navigateSpy = vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
    const compiled = fixture.nativeElement as HTMLElement;
    const acceptButton = Array.from(compiled.querySelectorAll<HTMLButtonElement>('button')).find(
      (button) => button.textContent?.includes('Accept'),
    );

    expect(acceptButton).not.toBeNull();

    acceptButton!.click();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(proposalService.approveCalls).toEqual([]);
    expect(compiled.textContent).toContain('Accept proposal?');

    const confirm = Array.from(
      compiled.querySelectorAll<HTMLButtonElement>('[role="dialog"] button'),
    ).find((button) => button.textContent?.trim() === 'Accept proposal');

    expect(confirm).not.toBeNull();

    confirm!.click();
    fixture.detectChanges();
    await fixture.whenStable();

    // The project is materialised straight from the proposal: its title becomes the
    // project title and purpose, and the requested period becomes its dates.
    expect(proposalService.approveCalls).toEqual([
      {
        proposalId: 'proposal-1',
        payload: {
          title: 'Photographic history of Rio de Janeiro port, 1890-1930',
          purpose: 'Photographic history of Rio de Janeiro port, 1890-1930',
          beginDate: '2026-07-01',
          endDate: '2026-12-31',
          note: 'Accepted from my assignment detail.',
        },
      },
    ]);
    expect(navigateSpy).toHaveBeenCalledWith(['/p/collections/proposals/approved']);
  });

  it('requires a reason before rejecting the assignment', async () => {
    const fixture = TestBed.createComponent(ProposalMyDetailPageComponent);
    const componentRef: ComponentRef<ProposalMyDetailPageComponent> = fixture.componentRef;

    componentRef.setInput('id', 'proposal-1');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    await selectPanel(fixture, 'Actions');

    const compiled = fixture.nativeElement as HTMLElement;
    const rejectButton = Array.from(compiled.querySelectorAll<HTMLButtonElement>('button')).find(
      (button) => button.textContent?.trim() === 'Reject',
    );

    expect(rejectButton).not.toBeNull();

    rejectButton!.click();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const dialog = compiled.querySelector<HTMLElement>('[role="dialog"]');
    expect(dialog).not.toBeNull();
    expect(dialog!.textContent).toContain('Reject proposal?');

    const textarea = dialog!.querySelector<HTMLTextAreaElement>('#rejection-reason');
    const confirmBtn = Array.from(dialog!.querySelectorAll<HTMLButtonElement>('button')).find(
      (button) => button.textContent?.trim() === 'Reject proposal',
    );

    expect(textarea).not.toBeNull();
    expect(confirmBtn).not.toBeNull();
    expect(confirmBtn!.disabled).toBe(true);
    expect(proposalService.rejectCalls).toEqual([]);
  });

  it('rejects the assignment directly from the modal and navigates to the rejected list', async () => {
    const fixture = TestBed.createComponent(ProposalMyDetailPageComponent);
    const componentRef: ComponentRef<ProposalMyDetailPageComponent> = fixture.componentRef;

    componentRef.setInput('id', 'proposal-1');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    await selectPanel(fixture, 'Actions');

    const navigateSpy = vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
    const compiled = fixture.nativeElement as HTMLElement;
    const rejectButton = Array.from(compiled.querySelectorAll<HTMLButtonElement>('button')).find(
      (button) => button.textContent?.trim() === 'Reject',
    );

    rejectButton!.click();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const dialog = compiled.querySelector<HTMLElement>('[role="dialog"]');
    const textarea = dialog!.querySelector<HTMLTextAreaElement>('#rejection-reason');
    const confirmBtn = Array.from(dialog!.querySelectorAll<HTMLButtonElement>('button')).find(
      (button) => button.textContent?.trim() === 'Reject proposal',
    );

    textarea!.value = 'The request does not meet collection access criteria.';
    textarea!.dispatchEvent(new Event('input'));
    fixture.detectChanges();

    expect(confirmBtn!.disabled).toBe(false);

    confirmBtn!.click();
    fixture.detectChanges();
    await fixture.whenStable();

    expect(proposalService.rejectCalls).toEqual([
      {
        proposalId: 'proposal-1',
        payload: { reason: 'The request does not meet collection access criteria.' },
      },
    ]);
    expect(navigateSpy).toHaveBeenCalledWith(['/p/collections/proposals/rejected']);
  });
});
