import { ComponentRef } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { of } from 'rxjs';

import { ProposalStatus } from '@shared/models/collection-use-status.model';

import { RequestDocumentCorrectionsRequest } from '../../models/proposal-actions.model';
import { Document, DocumentCorrectionItem } from '../../models/proposal.model';
import { PROPOSAL_API_SERVICE } from '../../services/proposal-api.service';
import { ProposalDocumentsSectionComponent } from './proposal-documents-section.component';

function makeDoc(overrides: Partial<Document> = {}): Document {
  return {
    id: 'doc-1',
    type: 'REQUESTER_ATTACHMENT',
    fileName: 'report.pdf',
    submittedAt: '2026-06-01T10:00:00Z',
    submittedBy: {
      permissionId: 'perm-1',
      user: { id: 'u-1', name: 'Ada Citizen', email: 'ada@example.test' },
      group: 'EXTERNAL',
    },
    ...overrides,
  };
}

function makeCorrection(overrides: Partial<DocumentCorrectionItem> = {}): DocumentCorrectionItem {
  return {
    id: 'corr-1',
    documentType: 'REQUESTER_ATTACHMENT',
    reason: 'Illegible scan',
    status: 'REQUESTED',
    requestedAt: '2026-06-02T10:00:00Z',
    requestedBy: {
      permissionId: 'perm-2',
      user: { id: 'u-2', name: 'Grace Curator', email: 'grace@example.test' },
      group: 'COLLECTIONS_MANAGEMENT',
    },
    ...overrides,
  };
}

class ProposalApiStub {
  readonly downloadCalls: [string, string][] = [];

  downloadDocument(proposalId: string, documentId: string) {
    this.downloadCalls.push([proposalId, documentId]);
    return of(new Blob(['%PDF-1.4'], { type: 'application/pdf' }));
  }
}

interface SetupOptions {
  readonly status?: ProposalStatus;
  readonly correctionItems?: readonly DocumentCorrectionItem[];
}

describe('ProposalDocumentsSectionComponent', () => {
  let fixture: ComponentFixture<ProposalDocumentsSectionComponent>;
  let ref: ComponentRef<ProposalDocumentsSectionComponent>;
  let api: ProposalApiStub;

  async function setup(documents: Document[], options: SetupOptions = {}): Promise<HTMLElement> {
    api = new ProposalApiStub();
    await TestBed.configureTestingModule({
      imports: [ProposalDocumentsSectionComponent],
      providers: [{ provide: PROPOSAL_API_SERVICE, useValue: api }],
    }).compileComponents();

    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:mock');
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined);

    fixture = TestBed.createComponent(ProposalDocumentsSectionComponent);
    ref = fixture.componentRef;
    ref.setInput('proposalId', 'prop-1');
    ref.setInput('documents', documents);
    ref.setInput('status', options.status ?? 'SUBMITTED');
    ref.setInput('correctionItems', options.correctionItems ?? []);
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  function byText(el: HTMLElement, selector: string, text: string): HTMLButtonElement | undefined {
    return Array.from(el.querySelectorAll<HTMLButtonElement>(selector)).find((b) =>
      b.textContent?.includes(text),
    );
  }

  function type(el: HTMLElement, selector: string, value: string): void {
    const field = el.querySelector<HTMLTextAreaElement | HTMLInputElement>(selector)!;
    field.value = value;
    field.dispatchEvent(new Event('input'));
    // Flush CD so signal-driven [disabled] bindings settle before the next click
    // (a disabled button would swallow the click in the test DOM).
    fixture.detectChanges();
  }

  it('lists documents with a humanized type label', async () => {
    const el = await setup([makeDoc()]);
    expect(el.querySelector('.document__name')?.textContent).toContain('report.pdf');
    expect(el.querySelector('.document__type')?.textContent).toContain('Requester attachment');
  });

  it('shows an empty state when there are no documents', async () => {
    const el = await setup([]);
    expect(el.querySelector('.documents__empty')).not.toBeNull();
  });

  it('downloads a document through the service', async () => {
    const el = await setup([makeDoc()]);
    byText(el, '.document__btn', 'Download')!.click();
    await fixture.whenStable();

    expect(api.downloadCalls).toEqual([['prop-1', 'doc-1']]);
  });

  it('opens an iframe preview for a PDF', async () => {
    const el = await setup([makeDoc({ fileName: 'report.pdf' })]);
    byText(el, '.document__btn', 'Preview')!.click();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(el.querySelector('.preview')).not.toBeNull();
    expect(el.querySelector('iframe.preview__frame')).not.toBeNull();
  });

  it('shows the unsupported fallback for a .docx', async () => {
    const el = await setup([makeDoc({ id: 'doc-2', fileName: 'form.docx' })]);
    byText(el, '.document__btn', 'Preview')!.click();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(el.querySelector('.preview__unsupported')).not.toBeNull();
    expect(el.querySelector('iframe')).toBeNull();
    expect(api.downloadCalls).toEqual([]);
  });

  // Correction analysis

  it('hides the review actions when the proposal is not PENDING', async () => {
    const el = await setup([makeDoc()], { status: 'SUBMITTED' });
    expect(byText(el, '.document__btn', 'Request correction')).toBeUndefined();
    expect(byText(el, '.btn', 'Request a missing document')).toBeUndefined();
  });

  it('exposes the review actions when PENDING', async () => {
    const el = await setup([makeDoc()], { status: 'PENDING' });
    expect(byText(el, '.document__btn', 'Request correction')).toBeDefined();
    expect(byText(el, '.btn', 'Request a missing document')).toBeDefined();
  });

  it('flags a document that has an open correction', async () => {
    const el = await setup([makeDoc()], {
      status: 'PENDING',
      correctionItems: [makeCorrection({ documentId: 'doc-1' })],
    });
    expect(el.querySelector('.document--flagged')).not.toBeNull();
    expect(el.querySelector('.document__flag .badge--requested')?.textContent).toContain(
      'Marked for correction',
    );
    // A doc already flagged offers no second "Request correction".
    expect(byText(el, '.document__btn', 'Request correction')).toBeUndefined();
  });

  it('stages a per-document correction and a missing document, then emits one request', async () => {
    const el = await setup([makeDoc()], { status: 'PENDING' });
    const emitted: RequestDocumentCorrectionsRequest[] = [];
    ref.instance.correctionRequestSubmitted.subscribe((r) => emitted.push(r));

    // 1) Flag the existing document.
    byText(el, '.document__btn', 'Request correction')!.click();
    fixture.detectChanges();
    type(el, '.correction-form textarea', 'Blurry scan');
    byText(el, '.btn', 'Add to request')!.click();
    fixture.detectChanges();

    // 2) Request a missing document.
    byText(el, '.btn', 'Request a missing document')!.click();
    fixture.detectChanges();
    type(el, '#missing-type', 'INSURANCE_CERTIFICATE');
    type(el, '#missing-reason', 'Need the insurance certificate');
    byText(el, '.btn', 'Add to request')!.click();
    fixture.detectChanges();

    expect(el.querySelectorAll('.staging__item').length).toBe(2);

    // 3) Send a single request carrying both items.
    byText(el, '.btn', 'Send correction request')!.click();

    expect(emitted).toHaveLength(1);
    expect(emitted[0].items).toEqual([
      { documentType: 'REQUESTER_ATTACHMENT', reason: 'Blurry scan', documentId: 'doc-1' },
      {
        documentType: 'INSURANCE_CERTIFICATE',
        reason: 'Need the insurance certificate',
        documentId: undefined,
      },
    ]);
  });

  it('clears the local draft when the reset version bumps', async () => {
    const el = await setup([makeDoc()], { status: 'PENDING' });
    byText(el, '.document__btn', 'Request correction')!.click();
    fixture.detectChanges();
    type(el, '.correction-form textarea', 'Blurry scan');
    byText(el, '.btn', 'Add to request')!.click();
    fixture.detectChanges();
    expect(el.querySelectorAll('.staging__item').length).toBe(1);

    ref.setInput('correctionResetVersion', 1);
    fixture.detectChanges();

    expect(el.querySelector('.staging')).toBeNull();
  });

  it('renders resolved corrections in the panel', async () => {
    const el = await setup([], {
      status: 'PENDING',
      correctionItems: [
        makeCorrection({ id: 'corr-r', status: 'RESOLVED', resolvedAt: '2026-06-05T10:00:00Z' }),
      ],
    });
    expect(el.querySelector('.corrections')).not.toBeNull();
    expect(el.querySelector('.corrections__item .badge--resolved')?.textContent).toContain(
      'Resolved',
    );
  });

  it('links correction history entries back to their document row', async () => {
    const scrollIntoView = vi.fn();
    Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
      configurable: true,
      value: scrollIntoView,
    });

    const el = await setup([makeDoc()], {
      status: 'PENDING',
      correctionItems: [makeCorrection({ documentId: 'doc-1' })],
    });

    const link = byText(el, '.corrections__document-link', 'Show document: report.pdf');
    expect(link).toBeDefined();

    link!.click();
    fixture.detectChanges();

    expect(el.querySelector('#doc-row-doc-1')?.classList).toContain('document--highlighted');
    expect(scrollIntoView).toHaveBeenCalled();
  });
});
