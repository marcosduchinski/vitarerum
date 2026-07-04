import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap } from '@angular/router';
import { of } from 'rxjs';

import { PublicAmendmentDocument, PublicAmendmentView } from '../models/public-proposal.model';
import { PUBLIC_PROPOSAL_API_SERVICE } from '../services/public-proposal-api.service';
import { PublicSubmissionEditPageComponent } from './public-submission-edit-page.component';

class PublicProposalApiStub {
  readonly uploadCalls: [string, string, File][] = [];

  getAmendment() {
    return of<PublicAmendmentView>({
      referenceNumber: 'VRP-DEMO-0001',
      status: 'PENDING',
      expiresAt: '2026-07-10T10:00:00Z',
      correctionItems: [
        {
          id: 'corr-1',
          documentType: 'Insurance certificate',
          reason: 'Please attach the insurance certificate.',
          status: 'REQUESTED',
          documentId: null,
        },
      ],
      documents: [],
    });
  }

  addAmendmentDocument(token: string, documentType: string, file: File) {
    this.uploadCalls.push([token, documentType, file]);
    return of<PublicAmendmentDocument>({ id: 'doc-new', type: documentType, fileName: file.name });
  }

  deleteAmendmentDocument() {
    return of(undefined);
  }

  submitAmendment() {
    return of({ status: 'SUBMITTED' as const });
  }
}

describe('PublicSubmissionEditPageComponent', () => {
  let fixture: ComponentFixture<PublicSubmissionEditPageComponent>;
  let api: PublicProposalApiStub;

  async function setup(): Promise<HTMLElement> {
    api = new PublicProposalApiStub();
    await TestBed.configureTestingModule({
      imports: [PublicSubmissionEditPageComponent],
      providers: [
        { provide: PUBLIC_PROPOSAL_API_SERVICE, useValue: api },
        {
          provide: ActivatedRoute,
          useValue: { snapshot: { queryParamMap: convertToParamMap({ token: 'tok-1' }) } },
        },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(PublicSubmissionEditPageComponent);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  it('shows the requested document type as free-text, verbatim', async () => {
    const el = await setup();
    expect(el.querySelector('.correction-item__type')?.textContent).toContain(
      'Insurance certificate',
    );
  });

  it('uploads with the exact requested documentType (spaces preserved)', async () => {
    const el = await setup();
    const file = new File(['%PDF-1.4'], 'certificate.pdf', { type: 'application/pdf' });
    const input = el.querySelector<HTMLInputElement>('input[type="file"]')!;
    Object.defineProperty(input, 'files', { value: [file], configurable: true });
    input.dispatchEvent(new Event('change'));
    fixture.detectChanges();

    Array.from(el.querySelectorAll<HTMLButtonElement>('.edit-button'))
      .find((b) => b.textContent?.includes('Upload file'))!
      .click();
    await fixture.whenStable();

    expect(api.uploadCalls).toEqual([['tok-1', 'Insurance certificate', file]]);
  });
});
