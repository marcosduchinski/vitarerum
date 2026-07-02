import { ComponentRef } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { of } from 'rxjs';

import { Document } from '../../models/proposal.model';
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

class ProposalApiStub {
  readonly downloadCalls: [string, string][] = [];

  downloadDocument(proposalId: string, documentId: string) {
    this.downloadCalls.push([proposalId, documentId]);
    return of(new Blob(['%PDF-1.4'], { type: 'application/pdf' }));
  }
}

describe('ProposalDocumentsSectionComponent', () => {
  let fixture: ComponentFixture<ProposalDocumentsSectionComponent>;
  let ref: ComponentRef<ProposalDocumentsSectionComponent>;
  let api: ProposalApiStub;

  async function setup(documents: Document[]): Promise<HTMLElement> {
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
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
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
    const buttons = Array.from(el.querySelectorAll<HTMLButtonElement>('.document__btn'));
    const download = buttons.find((b) => b.textContent?.includes('Download'))!;
    download.click();
    await fixture.whenStable();

    expect(api.downloadCalls).toEqual([['prop-1', 'doc-1']]);
  });

  it('opens an iframe preview for a PDF', async () => {
    const el = await setup([makeDoc({ fileName: 'report.pdf' })]);
    const preview = Array.from(el.querySelectorAll<HTMLButtonElement>('.document__btn')).find((b) =>
      b.textContent?.includes('Preview'),
    )!;
    preview.click();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(el.querySelector('.preview')).not.toBeNull();
    expect(el.querySelector('iframe.preview__frame')).not.toBeNull();
  });

  it('shows the unsupported fallback for a .docx', async () => {
    const el = await setup([makeDoc({ id: 'doc-2', fileName: 'form.docx' })]);
    const preview = Array.from(el.querySelectorAll<HTMLButtonElement>('.document__btn')).find((b) =>
      b.textContent?.includes('Preview'),
    )!;
    preview.click();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(el.querySelector('.preview__unsupported')).not.toBeNull();
    expect(el.querySelector('iframe')).toBeNull();
    // A .docx preview must not fetch the file bytes.
    expect(api.downloadCalls).toEqual([]);
  });
});
