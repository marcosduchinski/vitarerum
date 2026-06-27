import { TestBed } from '@angular/core/testing';
import { of, throwError } from 'rxjs';

import { REPORTS_API_SERVICE } from '../../services/reports-api.service';
import { InSituVisitCidocDialogComponent } from './in-situ-visit-cidoc-dialog.component';

const CIDOC_DOCUMENT = {
  '@context': { crm: 'http://www.cidoc-crm.org/cidoc-crm/' },
  '@graph': [
    {
      '@id': 'ex:visit/record-1',
      '@type': 'crm:E7_Activity',
      'rdfs:label': 'In situ visit CUP-0001',
    },
  ],
};

describe('InSituVisitCidocDialogComponent', () => {
  const getCidocCrm = vi.fn();

  beforeEach(async () => {
    getCidocCrm.mockReset();
    getCidocCrm.mockReturnValue(of(CIDOC_DOCUMENT));
    await TestBed.configureTestingModule({
      imports: [InSituVisitCidocDialogComponent],
      providers: [
        {
          provide: REPORTS_API_SERVICE,
          useValue: { getInSituVisitCidocCrm: getCidocCrm },
        },
      ],
    }).compileComponents();
  });

  it('loads and presents formatted JSON-LD only when opened', async () => {
    const fixture = TestBed.createComponent(InSituVisitCidocDialogComponent);
    fixture.componentRef.setInput('recordId', 'record-1');
    fixture.detectChanges();
    expect(getCidocCrm).not.toHaveBeenCalled();

    fixture.componentRef.setInput('open', true);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(getCidocCrm).toHaveBeenCalledOnce();
    expect(getCidocCrm).toHaveBeenCalledWith('record-1');
    const code = (fixture.nativeElement as HTMLElement).querySelector(
      '[aria-label="CIDOC-CRM JSON-LD document"]',
    );
    expect(code?.textContent).toContain('"@type": "crm:E7_Activity"');
  });

  it('retries a failed request without closing the dialog', async () => {
    getCidocCrm
      .mockReturnValueOnce(
        throwError(() => ({ status: 503, error: 'SERVICE_UNAVAILABLE', message: 'Unavailable' })),
      )
      .mockReturnValueOnce(of(CIDOC_DOCUMENT));
    const fixture = TestBed.createComponent(InSituVisitCidocDialogComponent);
    fixture.componentRef.setInput('recordId', 'record-1');
    fixture.componentRef.setInput('open', true);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const retry = (fixture.nativeElement as HTMLElement).querySelector<HTMLButtonElement>(
      'app-error-message button',
    );
    retry?.click();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(getCidocCrm).toHaveBeenCalledTimes(2);
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('crm:E7_Activity');
  });

  it('copies the formatted document and announces completion', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(window.navigator, 'clipboard', {
      configurable: true,
      value: { writeText },
    });
    const fixture = TestBed.createComponent(InSituVisitCidocDialogComponent);
    fixture.componentRef.setInput('recordId', 'record-1');
    fixture.componentRef.setInput('open', true);
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const copy = (fixture.nativeElement as HTMLElement).querySelector<HTMLButtonElement>(
      '.cidoc-dialog__button--primary',
    );
    copy?.click();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(writeText).toHaveBeenCalledWith(JSON.stringify(CIDOC_DOCUMENT, null, 2));
    expect((fixture.nativeElement as HTMLElement).textContent).toContain(
      'JSON-LD copied to clipboard.',
    );
  });

  it('emits one controlled close request', () => {
    const fixture = TestBed.createComponent(InSituVisitCidocDialogComponent);
    const closed = vi.fn();
    fixture.componentInstance.closed.subscribe(closed);
    fixture.componentRef.setInput('recordId', 'record-1');
    fixture.componentRef.setInput('open', true);
    fixture.detectChanges();

    const close = (fixture.nativeElement as HTMLElement).querySelector<HTMLButtonElement>(
      '[aria-label="Close CIDOC-CRM viewer"]',
    );
    close?.click();

    expect(closed).toHaveBeenCalledOnce();
  });
});
