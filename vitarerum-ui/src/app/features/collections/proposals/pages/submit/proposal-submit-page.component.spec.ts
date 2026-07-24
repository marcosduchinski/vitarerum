import { provideRouter, Router } from '@angular/router';
import { TestBed } from '@angular/core/testing';
import { of } from 'rxjs';

import { DocumentTemplate } from '@features/admin/models/document-template.model';
import { DOCUMENT_TEMPLATE_MANAGEMENT_SERVICE } from '@features/admin/services/document-template-management.service';
import { CreateProposalRequest, CreateProposalResponse } from '../../models/proposal.model';
import { PROPOSAL_API_SERVICE } from '../../services/proposal-api.service';
import { ProposalSubmitPageComponent } from './proposal-submit-page.component';

class ProposalApiServiceStub {
  readonly createCalls: CreateProposalRequest[] = [];

  createProposal(request: CreateProposalRequest) {
    this.createCalls.push(request);
    return of<CreateProposalResponse>({
      proposal: {
        id: 'proposal-1',
        referenceNumber: 'VRP-20260618-0001',
        title: 'Collection use request: palaeontology specimen records',
        status: 'SUBMITTED',
        type: 'OTHER',
        submissionChannel: 'AUTHENTICATED',
        requestedBy: {
          permissionId: 'permission-external',
          user: { id: 'user-1', name: 'Alice Ferreira', email: 'alice@example.test' },
          group: 'EXTERNAL',
        },
        assignedTo: null,
        submittedAt: '2026-06-18T10:00:00',
      },
      conversationId: 'conversation-1',
    });
  }
}

class DocumentTemplateManagementServiceStub {
  readonly listCalls: string[] = [];

  list(useType?: string) {
    this.listCalls.push(useType ?? '');
    return of<DocumentTemplate[]>(
      useType === 'IN_SITU_VISIT'
        ? [
            {
              id: 'tpl-safety',
              useType: 'IN_SITU_VISIT',
              title: 'In-situ visit safety form',
              description: 'Download, complete and sign before your visit.',
              mandatory: true,
              active: true,
              displayOrder: 0,
              fileName: 'safety-form.docx',
              uploadedAt: '2026-06-01T09:00:00Z',
            },
            {
              id: 'tpl-inactive',
              useType: 'IN_SITU_VISIT',
              title: 'Inactive form',
              description: '',
              mandatory: false,
              active: false,
              displayOrder: 1,
              fileName: 'inactive.docx',
              uploadedAt: '2026-06-01T09:00:00Z',
            },
          ]
        : [],
    );
  }

  downloadFile() {
    return of(
      new Blob(['template'], {
        type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      }),
    );
  }
}

describe('ProposalSubmitPageComponent', () => {
  let proposalService: ProposalApiServiceStub;
  let templateService: DocumentTemplateManagementServiceStub;
  let router: Router;

  beforeEach(async () => {
    proposalService = new ProposalApiServiceStub();
    templateService = new DocumentTemplateManagementServiceStub();

    await TestBed.configureTestingModule({
      imports: [ProposalSubmitPageComponent],
      providers: [
        provideRouter([]),
        { provide: PROPOSAL_API_SERVICE, useValue: proposalService },
        { provide: DOCUMENT_TEMPLATE_MANAGEMENT_SERVICE, useValue: templateService },
      ],
    }).compileComponents();

    router = TestBed.inject(Router);
    vi.spyOn(router, 'navigate').mockResolvedValue(true);
  });

  it('renders authenticated request details and opening message fields', () => {
    const fixture = TestBed.createComponent(ProposalSubmitPageComponent);
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;

    expect(compiled.textContent).toContain('Request details');
    expect(compiled.textContent).toContain('Opening message');
    expect(compiled.textContent).toContain('Supporting documents');
    expect(compiled.querySelector('#useType')).not.toBeNull();
    expect(compiled.querySelector('#proposedBeginDate')).not.toBeNull();
    expect(compiled.querySelector('#proposedEndDate')).not.toBeNull();
    expect(compiled.querySelector('#subject')).not.toBeNull();
    expect(compiled.querySelector('#body')).not.toBeNull();
    expect(compiled.querySelector('#documents')).not.toBeNull();
    expect(compiled.querySelector('#recipient')).toBeNull();
    expect(compiled.querySelector('#title')).toBeNull();
    expect(compiled.querySelector('#purpose')).toBeNull();
  });

  it('shows active required document templates when in-situ visit is selected', async () => {
    const fixture = TestBed.createComponent(ProposalSubmitPageComponent);
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;

    expect(compiled.querySelector('.templates')).toBeNull();

    setSelectValue(compiled, '#useType', 'IN_SITU_VISIT');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(templateService.listCalls).toContain('IN_SITU_VISIT');
    expect(compiled.textContent).toContain('Required documents');
    expect(compiled.textContent).toContain('In-situ visit safety form');
    expect(compiled.textContent).toContain('Mandatory');
    expect(compiled.textContent).not.toContain('Inactive form');
  });

  it('warns and blocks exhibition and other intended uses', async () => {
    const fixture = TestBed.createComponent(ProposalSubmitPageComponent);
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;
    const document = new File(['support'], 'support.pdf', { type: 'application/pdf' });
    const noticeText = 'Only in-situ visit requests are operational at the moment.';

    setSelectValue(compiled, '#useType', 'EXHIBITION');
    setInputValue(compiled, '#proposedBeginDate', '2026-06-01');
    setInputValue(compiled, '#proposedEndDate', '2026-06-07');
    setInputValue(compiled, '#subject', 'Archive access request');
    setInputValue(compiled, '#body', 'I would like to discuss access to archive materials.');
    setFileInput(compiled, '#documents', [document]);
    fixture.detectChanges();

    expect(compiled.textContent).toContain(noticeText);

    compiled
      .querySelector<HTMLFormElement>('form')
      ?.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    fixture.detectChanges();
    await fixture.whenStable();

    expect(proposalService.createCalls).toHaveLength(0);

    setSelectValue(compiled, '#useType', 'OTHER');
    fixture.detectChanges();

    expect(compiled.textContent).toContain(noticeText);
  });

  it('submits request details, opening message, and documents', async () => {
    const fixture = TestBed.createComponent(ProposalSubmitPageComponent);
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    const document = new File(['support'], 'support.pdf', { type: 'application/pdf' });
    setSelectValue(compiled, '#useType', 'IN_SITU_VISIT');
    setInputValue(compiled, '#proposedBeginDate', '2026-06-01');
    setInputValue(compiled, '#proposedEndDate', '2026-06-07');
    setInputValue(compiled, '#subject', 'Archive access request');
    setInputValue(compiled, '#body', 'I would like to discuss access to archive materials.');
    setFileInput(compiled, '#documents', [document]);

    compiled
      .querySelector<HTMLFormElement>('form')
      ?.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    fixture.detectChanges();
    await fixture.whenStable();

    expect(proposalService.createCalls).toEqual([
      {
        intendedUse: 'IN_SITU_VISIT',
        beginDate: '2026-06-01',
        endDate: '2026-06-07',
        initialMessageSubject: 'Archive access request',
        initialMessageBody: 'I would like to discuss access to archive materials.',
        documents: [document],
      },
    ]);
    expect(router.navigate).toHaveBeenCalledWith(['/p/collections/proposals', 'proposal-1'], {
      queryParams: {
        returnTo: '/p/collections/proposals/submit',
        returnLabel: 'submit proposal',
      },
    });
  });

  it('blocks submission until at least one supporting document is attached', () => {
    const fixture = TestBed.createComponent(ProposalSubmitPageComponent);
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    setSelectValue(compiled, '#useType', 'IN_SITU_VISIT');
    setInputValue(compiled, '#proposedBeginDate', '2026-06-01');
    setInputValue(compiled, '#proposedEndDate', '2026-06-07');
    setInputValue(compiled, '#subject', 'Archive access request');
    setInputValue(compiled, '#body', 'I would like to discuss access to archive materials.');

    compiled
      .querySelector<HTMLFormElement>('form')
      ?.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    fixture.detectChanges();

    expect(proposalService.createCalls).toHaveLength(0);
    expect(compiled.textContent).toContain('Attach at least one supporting document.');
  });

  it('blocks submission when the opening message is incomplete', () => {
    const fixture = TestBed.createComponent(ProposalSubmitPageComponent);
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    setSelectValue(compiled, '#useType', 'IN_SITU_VISIT');
    setInputValue(compiled, '#proposedBeginDate', '2026-06-01');
    setInputValue(compiled, '#proposedEndDate', '2026-06-07');
    setInputValue(compiled, '#subject', '');

    compiled
      .querySelector<HTMLFormElement>('form')
      ?.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    fixture.detectChanges();

    expect(proposalService.createCalls).toHaveLength(0);
    expect(compiled.textContent).toContain('Subject is required.');
  });
});

function setInputValue(root: HTMLElement, selector: string, value: string): void {
  const field = root.querySelector<HTMLInputElement | HTMLTextAreaElement>(selector);
  expect(field).not.toBeNull();
  field!.value = value;
  field!.dispatchEvent(new Event('input', { bubbles: true }));
}

function setSelectValue(root: HTMLElement, selector: string, value: string): void {
  const field = root.querySelector<HTMLSelectElement>(selector);
  expect(field).not.toBeNull();
  field!.value = value;
  field!.dispatchEvent(new Event('change', { bubbles: true }));
}

function setFileInput(root: HTMLElement, selector: string, files: readonly File[]): void {
  const field = root.querySelector<HTMLInputElement>(selector);
  expect(field).not.toBeNull();
  Object.defineProperty(field, 'files', {
    configurable: true,
    value: files,
  });
  field!.dispatchEvent(new Event('change', { bubbles: true }));
}
