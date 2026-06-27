import { provideRouter, Router } from '@angular/router';
import { TestBed } from '@angular/core/testing';
import { of } from 'rxjs';

import {
  CreateProposalRequest,
  CreateProposalResponse,
} from '../../models/proposal.model';
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

describe('ProposalSubmitPageComponent', () => {
  let proposalService: ProposalApiServiceStub;
  let router: Router;

  beforeEach(async () => {
    proposalService = new ProposalApiServiceStub();

    await TestBed.configureTestingModule({
      imports: [ProposalSubmitPageComponent],
      providers: [
        provideRouter([]),
        { provide: PROPOSAL_API_SERVICE, useValue: proposalService },
      ],
    }).compileComponents();

    router = TestBed.inject(Router);
    vi.spyOn(router, 'navigate').mockResolvedValue(true);
  });

  it('renders only the opening message fields', () => {
    const fixture = TestBed.createComponent(ProposalSubmitPageComponent);
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;

    expect(compiled.textContent).toContain('Opening message');
    expect(compiled.querySelector('#recipient')).not.toBeNull();
    expect(compiled.querySelector('#subject')).not.toBeNull();
    expect(compiled.querySelector('#body')).not.toBeNull();
    expect(compiled.querySelector('#title')).toBeNull();
    expect(compiled.querySelector('#purpose')).toBeNull();
    expect(compiled.querySelector('#begin-date')).toBeNull();
    expect(compiled.querySelector('#end-date')).toBeNull();
    expect(compiled.querySelector('input[name="type"]')).toBeNull();
  });

  it('submits only the opening message fields', async () => {
    const fixture = TestBed.createComponent(ProposalSubmitPageComponent);
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    setInputValue(compiled, '#recipient', 'collections@example.test');
    setInputValue(compiled, '#subject', 'Archive access request');
    setInputValue(compiled, '#body', 'I would like to discuss access to archive materials.');

    compiled.querySelector<HTMLFormElement>('form')?.dispatchEvent(
      new Event('submit', { bubbles: true, cancelable: true }),
    );
    fixture.detectChanges();
    await fixture.whenStable();

    expect(proposalService.createCalls).toEqual([
      {
        initialMessageRecipient: 'collections@example.test',
        initialMessageSubject: 'Archive access request',
        initialMessageBody: 'I would like to discuss access to archive materials.',
      },
    ]);
    expect(router.navigate).toHaveBeenCalledWith(['/p/collections/proposals', 'proposal-1'], {
      queryParams: {
        returnTo: '/p/collections/proposals/submit',
        returnLabel: 'submit proposal',
      },
    });
  });

  it('blocks submission when the opening message is incomplete', () => {
    const fixture = TestBed.createComponent(ProposalSubmitPageComponent);
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    setInputValue(compiled, '#subject', '');

    compiled.querySelector<HTMLFormElement>('form')?.dispatchEvent(
      new Event('submit', { bubbles: true, cancelable: true }),
    );
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
