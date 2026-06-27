import { ComponentRef } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { of } from 'rxjs';

import { Message, ProposalDetail } from '../../models/proposal.model';
import { PROPOSAL_API_SERVICE } from '../../services/proposal-api.service';
import {
  ProposalConversationSectionComponent,
  ReplyComposerPayload,
} from './proposal-conversation-section.component';

const proposalServiceStub = {
  downloadDocument: () => of(new Blob(['mock'])),
};

const PROPOSAL: ProposalDetail = {
  id: 'proposal-1',
  referenceNumber: 'VR-2026-001',
  title: 'Photographic history of Rio de Janeiro port, 1890-1930',
  status: 'PENDING',
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
    title: 'Photographic history of Rio de Janeiro port, 1890-1930',
    status: 'CREATED',
  },
  submittedAt: '2026-05-01T10:00:00',
  conversationId: 'conversation-1',
  documents: [],
  requestedObjects: [],
};

const PROPOSAL_WITH_REQUESTED_OBJECTS: ProposalDetail = {
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
    {
      id: 'requested-object-2',
      objectReference: {
        inventoryNumber: 'MNHN-2026-002',
        displayTitle: 'Iberian lynx skull',
        objectName: 'Lynx pardinus',
        briefDescriptionSnapshot: null,
      },
      category: 'Zoology',
      description: '',
      requestedAt: '2026-05-01T10:00:00',
      requestedBy: PROPOSAL.requestedBy,
    },
  ],
};

const MESSAGES: readonly Message[] = [
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
    body: '<p>Attached response.</p>',
    attachments: [{ documentId: 'document-1', fileName: 'signed-response.docx' }],
  },
];

function setRequiredInputs(
  componentRef: ComponentRef<ProposalConversationSectionComponent>,
  resetVersion = 0,
): void {
  componentRef.setInput('proposal', PROPOSAL);
  componentRef.setInput('messages', MESSAGES);
  componentRef.setInput('messagesLoading', false);
  componentRef.setInput('sendingMessage', false);
  componentRef.setInput('messageError', null);
  componentRef.setInput('replyResetVersion', resetVersion);
}

describe('ProposalConversationSectionComponent', () => {
  it('hides the requested-object control when the proposal has no requested objects', async () => {
    await TestBed.configureTestingModule({
      imports: [ProposalConversationSectionComponent],
      providers: [{ provide: PROPOSAL_API_SERVICE, useValue: proposalServiceStub }],
    }).compileComponents();

    const fixture = TestBed.createComponent(ProposalConversationSectionComponent);
    setRequiredInputs(fixture.componentRef);
    fixture.componentRef.setInput('showRequestedObjectPicker', true);
    fixture.detectChanges();
    await fixture.whenStable();

    expect(
      (fixture.nativeElement as HTMLElement).querySelector('.requested-object-disclosure'),
    ).toBeNull();
  });

  it('does not expose the requested-object control unless its staff-only input is enabled', async () => {
    await TestBed.configureTestingModule({
      imports: [ProposalConversationSectionComponent],
      providers: [{ provide: PROPOSAL_API_SERVICE, useValue: proposalServiceStub }],
    }).compileComponents();

    const fixture = TestBed.createComponent(ProposalConversationSectionComponent);
    setRequiredInputs(fixture.componentRef);
    fixture.componentRef.setInput('proposal', PROPOSAL_WITH_REQUESTED_OBJECTS);
    fixture.detectChanges();
    await fixture.whenStable();

    expect(
      (fixture.nativeElement as HTMLElement).querySelector('.requested-object-disclosure'),
    ).toBeNull();
  });

  it('shows the staff requested-object control collapsed and toggles it accessibly', async () => {
    await TestBed.configureTestingModule({
      imports: [ProposalConversationSectionComponent],
      providers: [{ provide: PROPOSAL_API_SERVICE, useValue: proposalServiceStub }],
    }).compileComponents();

    const fixture = TestBed.createComponent(ProposalConversationSectionComponent);
    setRequiredInputs(fixture.componentRef);
    fixture.componentRef.setInput('proposal', PROPOSAL_WITH_REQUESTED_OBJECTS);
    fixture.componentRef.setInput('showRequestedObjectPicker', true);
    fixture.detectChanges();
    await fixture.whenStable();

    const compiled = fixture.nativeElement as HTMLElement;
    const toggle = compiled.querySelector<HTMLButtonElement>(
      '[aria-controls="requested-object-picker-panel"]',
    );

    expect(toggle?.getAttribute('aria-expanded')).toBe('false');
    expect(toggle?.querySelector('.pi-chevron-right')).not.toBeNull();
    expect(compiled.querySelector('#requested-object-picker-panel')).toBeNull();

    toggle!.click();
    fixture.detectChanges();

    expect(toggle?.getAttribute('aria-expanded')).toBe('true');
    expect(toggle?.querySelector('.pi-chevron-down')).not.toBeNull();
    expect(compiled.querySelector('#requested-object-picker-panel')).not.toBeNull();

    compiled.querySelector<HTMLInputElement>('.requested-object-picker input')!.click();
    fixture.detectChanges();

    toggle!.click();
    fixture.detectChanges();

    expect(toggle?.getAttribute('aria-expanded')).toBe('false');
    expect(compiled.querySelector('#requested-object-picker-panel')).toBeNull();

    toggle!.click();
    fixture.detectChanges();

    expect(
      compiled.querySelector<HTMLInputElement>('.requested-object-picker input')?.checked,
    ).toBe(true);
  });

  it('inserts selected requested objects safely into the reply without duplicates', async () => {
    await TestBed.configureTestingModule({
      imports: [ProposalConversationSectionComponent],
      providers: [{ provide: PROPOSAL_API_SERVICE, useValue: proposalServiceStub }],
    }).compileComponents();

    const fixture = TestBed.createComponent(ProposalConversationSectionComponent);
    const componentRef: ComponentRef<ProposalConversationSectionComponent> = fixture.componentRef;
    const submitted: ReplyComposerPayload[] = [];

    setRequiredInputs(componentRef);
    componentRef.setInput('proposal', PROPOSAL_WITH_REQUESTED_OBJECTS);
    componentRef.setInput('showRequestedObjectPicker', true);
    fixture.componentInstance.replySubmitted.subscribe((payload) => submitted.push(payload));
    fixture.detectChanges();
    await fixture.whenStable();

    const compiled = fixture.nativeElement as HTMLElement;
    compiled
      .querySelector<HTMLButtonElement>('[aria-controls="requested-object-picker-panel"]')!
      .click();
    fixture.detectChanges();
    const checkboxes = Array.from(
      compiled.querySelectorAll<HTMLInputElement>(
        '.requested-object-picker input[type="checkbox"]',
      ),
    );
    const insertButton = compiled.querySelector<HTMLButtonElement>(
      '.requested-object-picker__insert',
    );
    const editor = compiled.querySelector<HTMLElement>('.reply-editor');
    const sendButton = Array.from(compiled.querySelectorAll<HTMLButtonElement>('button')).find(
      (button) => button.textContent?.includes('Send response'),
    );

    expect(checkboxes).toHaveLength(2);
    expect(insertButton?.disabled).toBe(true);

    checkboxes[0].checked = true;
    checkboxes[0].dispatchEvent(new Event('change'));
    fixture.detectChanges();
    insertButton!.click();
    fixture.detectChanges();

    expect(editor?.textContent).toContain('Requested objects');
    expect(editor?.textContent).toContain('MNHN-2026-001 — Iberian lynx specimen');
    expect(editor?.textContent).toContain('Lynx pardinus');
    expect(checkboxes[0].disabled).toBe(true);
    expect(insertButton?.disabled).toBe(true);
    expect(
      editor?.querySelectorAll('[data-requested-object-id="requested-object-1"]'),
    ).toHaveLength(1);

    sendButton!.click();

    expect(submitted).toEqual([
      {
        body: '<p><strong>Requested objects</strong></p><ul><li>MNHN-2026-001 — Iberian lynx specimen (Lynx pardinus; Adult study skin; Requested for comparative research)</li></ul>',
        files: [],
      },
    ]);

    componentRef.setInput('replyResetVersion', 1);
    fixture.detectChanges();
    await fixture.whenStable();

    expect(
      compiled
        .querySelector<HTMLButtonElement>('[aria-controls="requested-object-picker-panel"]')
        ?.getAttribute('aria-expanded'),
    ).toBe('false');
    expect(compiled.querySelector('#requested-object-picker-panel')).toBeNull();
  });

  it('renders requester and staff messages with roles and attachments', async () => {
    await TestBed.configureTestingModule({
      imports: [ProposalConversationSectionComponent],
      providers: [{ provide: PROPOSAL_API_SERVICE, useValue: proposalServiceStub }],
    }).compileComponents();

    const fixture = TestBed.createComponent(ProposalConversationSectionComponent);
    const componentRef: ComponentRef<ProposalConversationSectionComponent> = fixture.componentRef;

    setRequiredInputs(componentRef);
    fixture.detectChanges();
    await fixture.whenStable();

    const compiled = fixture.nativeElement as HTMLElement;
    const messages = Array.from(compiled.querySelectorAll<HTMLElement>('.message'));

    expect(messages).toHaveLength(2);
    expect(messages[0].textContent).toContain('Requester');
    expect(messages[0].querySelector('.pi-user')).not.toBeNull();
    expect(messages[1].textContent).toContain('COLLECTIONS MANAGEMENT');
    expect(messages[1].querySelector('.pi-briefcase')).not.toBeNull();
    expect(messages[1].textContent).toContain('signed-response.docx');
  });

  it('emits reply body and selected files, then clears when reset version changes', async () => {
    await TestBed.configureTestingModule({
      imports: [ProposalConversationSectionComponent],
      providers: [{ provide: PROPOSAL_API_SERVICE, useValue: proposalServiceStub }],
    }).compileComponents();

    const fixture = TestBed.createComponent(ProposalConversationSectionComponent);
    const componentRef: ComponentRef<ProposalConversationSectionComponent> = fixture.componentRef;
    const submitted: ReplyComposerPayload[] = [];

    setRequiredInputs(componentRef);
    fixture.componentInstance.replySubmitted.subscribe((payload) => submitted.push(payload));
    fixture.detectChanges();
    await fixture.whenStable();

    const compiled = fixture.nativeElement as HTMLElement;
    const editor = compiled.querySelector<HTMLElement>('.reply-editor');
    const fileInput = compiled.querySelector<HTMLInputElement>('#staff-response-files');
    const sendButton = Array.from(compiled.querySelectorAll<HTMLButtonElement>('button')).find(
      (button) => button.textContent?.includes('Send response'),
    );
    const file = new File(['signed'], 'signed-response.docx', {
      type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    });

    editor!.innerHTML = '<p>Please review the attached signed files.</p>';
    editor!.dispatchEvent(new Event('input'));
    Object.defineProperty(fileInput!, 'files', { value: [file], configurable: true });
    fileInput!.dispatchEvent(new Event('change'));
    fixture.detectChanges();

    sendButton!.click();

    expect(submitted).toEqual([
      {
        body: '<p>Please review the attached signed files.</p>',
        files: [file],
      },
    ]);

    componentRef.setInput('replyResetVersion', 1);
    fixture.detectChanges();
    await fixture.whenStable();

    expect(editor!.innerHTML).toBe('');
    expect(compiled.querySelector('.selected-files')).toBeNull();
  });

  it('strips unsafe markup from submitted reply bodies', async () => {
    await TestBed.configureTestingModule({
      imports: [ProposalConversationSectionComponent],
      providers: [{ provide: PROPOSAL_API_SERVICE, useValue: proposalServiceStub }],
    }).compileComponents();

    const fixture = TestBed.createComponent(ProposalConversationSectionComponent);
    const componentRef: ComponentRef<ProposalConversationSectionComponent> = fixture.componentRef;
    const submitted: ReplyComposerPayload[] = [];

    setRequiredInputs(componentRef);
    fixture.componentInstance.replySubmitted.subscribe((payload) => submitted.push(payload));
    fixture.detectChanges();
    await fixture.whenStable();

    const compiled = fixture.nativeElement as HTMLElement;
    const editor = compiled.querySelector<HTMLElement>('.reply-editor');
    const sendButton = Array.from(compiled.querySelectorAll<HTMLButtonElement>('button')).find(
      (button) => button.textContent?.includes('Send response'),
    );

    editor!.innerHTML =
      '<p onclick="alert(1)">Safe <strong data-id="1">bold</strong><script>alert(1)</script></p><img src=x onerror=alert(1)><a href="javascript:alert(1)">link</a>';
    editor!.dispatchEvent(new Event('input'));
    fixture.detectChanges();

    sendButton!.click();

    expect(submitted).toEqual([
      {
        body: '<p>Safe <strong>bold</strong></p>link',
        files: [],
      },
    ]);
  });

  it('strips unsafe markup from rendered message bodies', async () => {
    await TestBed.configureTestingModule({
      imports: [ProposalConversationSectionComponent],
      providers: [{ provide: PROPOSAL_API_SERVICE, useValue: proposalServiceStub }],
    }).compileComponents();

    const fixture = TestBed.createComponent(ProposalConversationSectionComponent);
    const componentRef: ComponentRef<ProposalConversationSectionComponent> = fixture.componentRef;
    const unsafeMessages: readonly Message[] = [
      {
        id: 'unsafe-message',
        sentAt: '2026-05-01T11:00:00',
        sender: 'alice@example.test',
        recipient: 'Collections management',
        subject: 'Unsafe body',
        body: '<p style="color: red">Visible <em onclick="alert(1)">text</em><iframe src="https://example.test"></iframe></p><a href="javascript:alert(1)">link</a>',
      },
    ];

    setRequiredInputs(componentRef);
    componentRef.setInput('messages', unsafeMessages);
    fixture.detectChanges();
    await fixture.whenStable();

    const body = (fixture.nativeElement as HTMLElement).querySelector<HTMLElement>(
      '.message__body',
    );

    expect(body?.innerHTML).toBe('<p>Visible <em>text</em></p>link');
    expect(body?.querySelector('iframe')).toBeNull();
    expect(body?.querySelector('[style], [onclick], [href]')).toBeNull();
  });

  it('runs browser editor commands from formatting controls', async () => {
    await TestBed.configureTestingModule({
      imports: [ProposalConversationSectionComponent],
      providers: [{ provide: PROPOSAL_API_SERVICE, useValue: proposalServiceStub }],
    }).compileComponents();

    const execCommand = vi.fn();
    Object.defineProperty(document, 'execCommand', {
      value: execCommand,
      configurable: true,
    });
    const fixture = TestBed.createComponent(ProposalConversationSectionComponent);
    const componentRef: ComponentRef<ProposalConversationSectionComponent> = fixture.componentRef;

    setRequiredInputs(componentRef);
    fixture.detectChanges();
    await fixture.whenStable();

    const compiled = fixture.nativeElement as HTMLElement;
    const boldButton = compiled.querySelector<HTMLButtonElement>('[aria-label="Bold"]');

    boldButton!.click();

    expect(execCommand).toHaveBeenCalledWith('bold', false);
  });

  it('downloads an attachment via the proposal service when its button is clicked', async () => {
    const downloadDocument = vi.fn().mockReturnValue(of(new Blob(['file-bytes'])));
    const createObjectURL = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:mock');
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined);
    const clickSpy = vi
      .spyOn(HTMLAnchorElement.prototype, 'click')
      .mockImplementation(() => undefined);

    await TestBed.configureTestingModule({
      imports: [ProposalConversationSectionComponent],
      providers: [{ provide: PROPOSAL_API_SERVICE, useValue: { downloadDocument } }],
    }).compileComponents();

    const fixture = TestBed.createComponent(ProposalConversationSectionComponent);
    const componentRef: ComponentRef<ProposalConversationSectionComponent> = fixture.componentRef;

    setRequiredInputs(componentRef);
    fixture.detectChanges();
    await fixture.whenStable();

    const compiled = fixture.nativeElement as HTMLElement;
    const downloadButton = compiled.querySelector<HTMLButtonElement>(
      '[aria-label="Download signed-response.docx"]',
    );

    expect(downloadButton).not.toBeNull();

    downloadButton!.click();
    await fixture.whenStable();

    expect(downloadDocument).toHaveBeenCalledWith('proposal-1', 'document-1');
    expect(createObjectURL).toHaveBeenCalled();
    expect(clickSpy).toHaveBeenCalled();
  });

  it('hides triage message actions by default', async () => {
    await TestBed.configureTestingModule({
      imports: [ProposalConversationSectionComponent],
      providers: [{ provide: PROPOSAL_API_SERVICE, useValue: proposalServiceStub }],
    }).compileComponents();

    const fixture = TestBed.createComponent(ProposalConversationSectionComponent);
    const componentRef: ComponentRef<ProposalConversationSectionComponent> = fixture.componentRef;

    setRequiredInputs(componentRef);
    fixture.detectChanges();
    await fixture.whenStable();

    const compiled = fixture.nativeElement as HTMLElement;

    expect(compiled.querySelector('[aria-label^="Run intended-use triage"]')).toBeNull();
  });

  it('emits the selected message from triage actions when enabled', async () => {
    await TestBed.configureTestingModule({
      imports: [ProposalConversationSectionComponent],
      providers: [{ provide: PROPOSAL_API_SERVICE, useValue: proposalServiceStub }],
    }).compileComponents();

    const fixture = TestBed.createComponent(ProposalConversationSectionComponent);
    const componentRef: ComponentRef<ProposalConversationSectionComponent> = fixture.componentRef;
    const requested: Message[] = [];

    setRequiredInputs(componentRef);
    componentRef.setInput('showTriageAction', true);
    fixture.componentInstance.triageRequested.subscribe((message) => requested.push(message));
    fixture.detectChanges();
    await fixture.whenStable();

    const compiled = fixture.nativeElement as HTMLElement;
    const buttons = Array.from(
      compiled.querySelectorAll<HTMLButtonElement>('[aria-label^="Run intended-use triage"]'),
    );

    expect(buttons).toHaveLength(2);

    buttons[1].click();

    expect(requested).toEqual([MESSAGES[1]]);
  });
});
