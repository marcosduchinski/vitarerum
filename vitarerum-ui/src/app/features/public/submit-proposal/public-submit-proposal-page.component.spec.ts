import { TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { of } from 'rxjs';

import { TURNSTILE_SITE_KEY } from '@core/config/app-config.model';

import { UseType } from '@shared/models/collection-use-status.model';

import { PublicProposalSubmission } from '../models/public-proposal.model';
import { PUBLIC_DOCUMENT_TEMPLATE_API_SERVICE } from '../services/public-document-template-api.service';
import { PUBLIC_PROPOSAL_API_SERVICE } from '../services/public-proposal-api.service';
import { PublicSubmitProposalPageComponent } from './public-submit-proposal-page.component';

class PublicProposalApiStub {
  readonly submitCalls: PublicProposalSubmission[] = [];

  submit(submission: PublicProposalSubmission) {
    this.submitCalls.push(submission);
    return of({ status: 'PENDING_CONFIRMATION' as const, email: submission.citizenEmail });
  }

  confirm() {
    return of({ status: 'CONFIRMED' as const });
  }
}

class PublicDocumentTemplateApiStub {
  readonly listCalls: UseType[] = [];

  listTemplates(useType: UseType) {
    this.listCalls.push(useType);
    return of(
      useType === 'IN_SITU_VISIT'
        ? [{ id: 'tpl-1', title: 'Safety form', description: 'Fill in.', mandatory: true }]
        : [],
    );
  }

  downloadUrl(id: string) {
    return `/api/v1/public/document-templates/${id}/file`;
  }
}

describe('PublicSubmitProposalPageComponent', () => {
  let api: PublicProposalApiStub;
  let templates: PublicDocumentTemplateApiStub;
  let router: Router;

  async function setup(siteKey = ''): Promise<void> {
    api = new PublicProposalApiStub();
    templates = new PublicDocumentTemplateApiStub();

    await TestBed.configureTestingModule({
      imports: [PublicSubmitProposalPageComponent],
      providers: [
        provideRouter([]),
        { provide: PUBLIC_PROPOSAL_API_SERVICE, useValue: api },
        { provide: PUBLIC_DOCUMENT_TEMPLATE_API_SERVICE, useValue: templates },
        { provide: TURNSTILE_SITE_KEY, useValue: siteKey },
      ],
    }).compileComponents();

    router = TestBed.inject(Router);
    vi.spyOn(router, 'navigate').mockResolvedValue(true);
  }

  it('hides the captcha when no site key is configured', async () => {
    await setup('');
    const fixture = TestBed.createComponent(PublicSubmitProposalPageComponent);
    fixture.detectChanges();

    expect((fixture.nativeElement as HTMLElement).querySelector('app-turnstile')).toBeNull();
  });

  it('shows required document templates when a use type is selected', async () => {
    await setup('');
    const fixture = TestBed.createComponent(PublicSubmitProposalPageComponent);
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;

    expect(compiled.querySelector('.templates')).toBeNull();

    setSelectValue(compiled, '#useType', 'IN_SITU_VISIT');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(templates.listCalls).toContain('IN_SITU_VISIT');
    const section = compiled.querySelector('.templates');
    expect(section).not.toBeNull();
    const link = section?.querySelector<HTMLAnchorElement>('.templates__download');
    expect(link?.textContent).toContain('Safety form');
    expect(link?.getAttribute('href')).toBe('/api/v1/public/document-templates/tpl-1/file');
    expect(section?.querySelector('.templates__badge')?.textContent).toContain('Mandatory');
  });

  it('warns that exhibition and other intended uses are not operational yet', async () => {
    await setup('');
    const fixture = TestBed.createComponent(PublicSubmitProposalPageComponent);
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;
    const noticeText = 'Only in-situ visit requests are operational at the moment.';

    expect(compiled.textContent).not.toContain(noticeText);

    setSelectValue(compiled, '#useType', 'EXHIBITION');
    fixture.detectChanges();

    expect(compiled.textContent).toContain(noticeText);
    expect(compiled.textContent).toContain('will be implemented later');

    setSelectValue(compiled, '#useType', 'OTHER');
    fixture.detectChanges();

    expect(compiled.textContent).toContain(noticeText);

    setSelectValue(compiled, '#useType', 'IN_SITU_VISIT');
    fixture.detectChanges();

    expect(compiled.textContent).not.toContain(noticeText);
  });

  it('submits citizen details and routes to the confirmation screen', async () => {
    await setup('');
    const fixture = TestBed.createComponent(PublicSubmitProposalPageComponent);
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    setInputValue(compiled, '#name', 'Pedro Silva');
    setInputValue(compiled, '#email', 'pedro@example.test');
    setInputValue(compiled, '#subject', 'Access to the zoology collection');
    setInputValue(compiled, '#body', 'I would like to study a specimen for my thesis.');
    setSelectValue(compiled, '#useType', 'IN_SITU_VISIT');
    setInputValue(compiled, '#proposedBeginDate', '2026-07-01');
    setInputValue(compiled, '#proposedEndDate', '2026-07-15');
    setFiles(compiled, '#documents', [
      new File(['%PDF-1.4\n'], 'support.pdf', { type: 'application/pdf' }),
    ]);
    setChecked(compiled, '.consent input[type="checkbox"]', true);

    submitForm(compiled);
    fixture.detectChanges();
    await fixture.whenStable();

    expect(api.submitCalls).toHaveLength(1);
    expect(api.submitCalls[0]).toMatchObject({
      citizenName: 'Pedro Silva',
      citizenEmail: 'pedro@example.test',
      subject: 'Access to the zoology collection',
      useType: 'IN_SITU_VISIT',
      proposedBeginDate: '2026-07-01',
      proposedEndDate: '2026-07-15',
      consent: true,
      website: '', // honeypot stayed empty
    });
    expect(api.submitCalls[0].documents).toHaveLength(1);
    expect(api.submitCalls[0].documents[0].name).toBe('support.pdf');
    expect(router.navigate).toHaveBeenCalledWith(['/submit-proposal/received'], {
      queryParams: { email: 'pedro@example.test' },
    });
  });

  it('blocks submission until consent is given', async () => {
    await setup('');
    const fixture = TestBed.createComponent(PublicSubmitProposalPageComponent);
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    setInputValue(compiled, '#name', 'Pedro Silva');
    setInputValue(compiled, '#email', 'pedro@example.test');
    setInputValue(compiled, '#subject', 'Access request');
    setInputValue(compiled, '#body', 'Details about my request.');
    // consent intentionally left unchecked

    submitForm(compiled);
    fixture.detectChanges();

    expect(api.submitCalls).toHaveLength(0);
    expect(compiled.textContent).toContain('Consent is required to submit.');
  });

  it('submits the proposed dates', async () => {
    await setup('');
    const fixture = TestBed.createComponent(PublicSubmitProposalPageComponent);
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    setInputValue(compiled, '#name', 'Pedro Silva');
    setInputValue(compiled, '#email', 'pedro@example.test');
    setInputValue(compiled, '#subject', 'Access request');
    setInputValue(compiled, '#body', 'Details about my request.');
    setSelectValue(compiled, '#useType', 'IN_SITU_VISIT');
    setInputValue(compiled, '#proposedBeginDate', '2026-07-01');
    setInputValue(compiled, '#proposedEndDate', '2026-07-15');
    setFiles(compiled, '#documents', [
      new File(['%PDF-1.4\n'], 'support.pdf', { type: 'application/pdf' }),
    ]);
    setChecked(compiled, '.consent input[type="checkbox"]', true);

    submitForm(compiled);
    fixture.detectChanges();
    await fixture.whenStable();

    expect(api.submitCalls).toHaveLength(1);
    expect(api.submitCalls[0]).toMatchObject({
      proposedBeginDate: '2026-07-01',
      proposedEndDate: '2026-07-15',
    });
  });

  it('blocks submission until both proposed dates are provided', async () => {
    await setup('');
    const fixture = TestBed.createComponent(PublicSubmitProposalPageComponent);
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    setInputValue(compiled, '#name', 'Pedro Silva');
    setInputValue(compiled, '#email', 'pedro@example.test');
    setInputValue(compiled, '#subject', 'Access request');
    setInputValue(compiled, '#body', 'Details about my request.');
    setSelectValue(compiled, '#useType', 'OTHER');
    setChecked(compiled, '.consent input[type="checkbox"]', true);
    // proposed dates intentionally left empty

    submitForm(compiled);
    fixture.detectChanges();

    expect(api.submitCalls).toHaveLength(0);
    expect(compiled.textContent).toContain('Please give both a start and an end date.');
  });

  it('blocks submission until a supporting document is attached', async () => {
    await setup('');
    const fixture = TestBed.createComponent(PublicSubmitProposalPageComponent);
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    setInputValue(compiled, '#name', 'Pedro Silva');
    setInputValue(compiled, '#email', 'pedro@example.test');
    setInputValue(compiled, '#subject', 'Access request');
    setInputValue(compiled, '#body', 'Details about my request.');
    setSelectValue(compiled, '#useType', 'IN_SITU_VISIT');
    setInputValue(compiled, '#proposedBeginDate', '2026-07-01');
    setInputValue(compiled, '#proposedEndDate', '2026-07-15');
    setChecked(compiled, '.consent input[type="checkbox"]', true);

    submitForm(compiled);
    fixture.detectChanges();

    expect(api.submitCalls).toHaveLength(0);
    expect(compiled.textContent).toContain('Attach at least one supporting document.');
  });

  it('blocks more than five supporting documents', async () => {
    await setup('');
    const fixture = TestBed.createComponent(PublicSubmitProposalPageComponent);
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    setInputValue(compiled, '#name', 'Pedro Silva');
    setInputValue(compiled, '#email', 'pedro@example.test');
    setInputValue(compiled, '#subject', 'Access request');
    setInputValue(compiled, '#body', 'Details about my request.');
    setSelectValue(compiled, '#useType', 'IN_SITU_VISIT');
    setInputValue(compiled, '#proposedBeginDate', '2026-07-01');
    setInputValue(compiled, '#proposedEndDate', '2026-07-15');
    setChecked(compiled, '.consent input[type="checkbox"]', true);
    setFiles(
      compiled,
      '#documents',
      Array.from(
        { length: 6 },
        (_, index) => new File(['%PDF-1.4\n'], `support-${index}.pdf`, { type: 'application/pdf' }),
      ),
    );

    submitForm(compiled);
    fixture.detectChanges();

    expect(api.submitCalls).toHaveLength(0);
    expect(compiled.textContent).toContain('Attach no more than five supporting documents.');
  });

  it('blocks oversized supporting documents', async () => {
    await setup('');
    const fixture = TestBed.createComponent(PublicSubmitProposalPageComponent);
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    setInputValue(compiled, '#name', 'Pedro Silva');
    setInputValue(compiled, '#email', 'pedro@example.test');
    setInputValue(compiled, '#subject', 'Access request');
    setInputValue(compiled, '#body', 'Details about my request.');
    setSelectValue(compiled, '#useType', 'IN_SITU_VISIT');
    setInputValue(compiled, '#proposedBeginDate', '2026-07-01');
    setInputValue(compiled, '#proposedEndDate', '2026-07-15');
    setChecked(compiled, '.consent input[type="checkbox"]', true);
    setFiles(compiled, '#documents', [
      new File([new Uint8Array(10 * 1024 * 1024 + 1)], 'large.pdf', {
        type: 'application/pdf',
      }),
    ]);

    submitForm(compiled);
    fixture.detectChanges();

    expect(api.submitCalls).toHaveLength(0);
    expect(compiled.textContent).toContain('large.pdf is larger than 10 MB.');
  });

  it('blocks submission when the end date precedes the start date', async () => {
    await setup('');
    const fixture = TestBed.createComponent(PublicSubmitProposalPageComponent);
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    setInputValue(compiled, '#name', 'Pedro Silva');
    setInputValue(compiled, '#email', 'pedro@example.test');
    setInputValue(compiled, '#subject', 'Access request');
    setInputValue(compiled, '#body', 'Details about my request.');
    setSelectValue(compiled, '#useType', 'IN_SITU_VISIT');
    setInputValue(compiled, '#proposedBeginDate', '2026-07-15');
    setInputValue(compiled, '#proposedEndDate', '2026-07-01');
    setChecked(compiled, '.consent input[type="checkbox"]', true);

    submitForm(compiled);
    fixture.detectChanges();

    expect(api.submitCalls).toHaveLength(0);
    expect(compiled.textContent).toContain("The end date can't be before the start date.");
  });

  it('blocks submission until an intended use is selected', async () => {
    await setup('');
    const fixture = TestBed.createComponent(PublicSubmitProposalPageComponent);
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    setInputValue(compiled, '#name', 'Pedro Silva');
    setInputValue(compiled, '#email', 'pedro@example.test');
    setInputValue(compiled, '#subject', 'Access request');
    setInputValue(compiled, '#body', 'Details about my request.');
    setChecked(compiled, '.consent input[type="checkbox"]', true);
    // intended use intentionally left unselected

    submitForm(compiled);
    fixture.detectChanges();

    expect(api.submitCalls).toHaveLength(0);
    expect(compiled.textContent).toContain("Please choose how you'll use the collection.");
  });

  it('rejects an invalid e-mail address', async () => {
    await setup('');
    const fixture = TestBed.createComponent(PublicSubmitProposalPageComponent);
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    setInputValue(compiled, '#name', 'Pedro Silva');
    setInputValue(compiled, '#email', 'not-an-email');
    setInputValue(compiled, '#subject', 'Access request');
    setInputValue(compiled, '#body', 'Details about my request.');
    setChecked(compiled, '.consent input[type="checkbox"]', true);

    submitForm(compiled);
    fixture.detectChanges();

    expect(api.submitCalls).toHaveLength(0);
    expect(compiled.textContent).toContain('A valid e-mail address is required.');
  });
});

function setInputValue(root: HTMLElement, selector: string, value: string): void {
  const field = root.querySelector<HTMLInputElement | HTMLTextAreaElement>(selector);
  expect(field).not.toBeNull();
  field!.value = value;
  field!.dispatchEvent(new Event('input', { bubbles: true }));
}

function setSelectValue(root: HTMLElement, selector: string, value: string): void {
  const select = root.querySelector<HTMLSelectElement>(selector);
  expect(select).not.toBeNull();
  select!.value = value;
  select!.dispatchEvent(new Event('change', { bubbles: true }));
}

function setChecked(root: HTMLElement, selector: string, checked: boolean): void {
  const box = root.querySelector<HTMLInputElement>(selector);
  expect(box).not.toBeNull();
  box!.checked = checked;
  box!.dispatchEvent(new Event('change', { bubbles: true }));
}

function setFiles(root: HTMLElement, selector: string, files: File[]): void {
  const input = root.querySelector<HTMLInputElement>(selector);
  expect(input).not.toBeNull();
  Object.defineProperty(input!, 'files', {
    value: files,
    configurable: true,
  });
  input!.dispatchEvent(new Event('change', { bubbles: true }));
}

function submitForm(root: HTMLElement): void {
  root
    .querySelector<HTMLFormElement>('form')
    ?.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
}
