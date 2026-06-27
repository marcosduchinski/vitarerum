import { TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { of } from 'rxjs';

import { TURNSTILE_SITE_KEY } from '@core/config/app-config.model';

import { PublicProposalSubmission } from '../models/public-proposal.model';
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

describe('PublicSubmitProposalPageComponent', () => {
  let api: PublicProposalApiStub;
  let router: Router;

  async function setup(siteKey = ''): Promise<void> {
    api = new PublicProposalApiStub();

    await TestBed.configureTestingModule({
      imports: [PublicSubmitProposalPageComponent],
      providers: [
        provideRouter([]),
        { provide: PUBLIC_PROPOSAL_API_SERVICE, useValue: api },
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

  it('submits citizen details and routes to the confirmation screen', async () => {
    await setup('');
    const fixture = TestBed.createComponent(PublicSubmitProposalPageComponent);
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    setInputValue(compiled, '#name', 'Pedro Silva');
    setInputValue(compiled, '#email', 'pedro@example.test');
    setInputValue(compiled, '#subject', 'Access to the zoology collection');
    setInputValue(compiled, '#body', 'I would like to study a specimen for my thesis.');
    setChecked(compiled, '.consent input[type="checkbox"]', true);

    submitForm(compiled);
    fixture.detectChanges();
    await fixture.whenStable();

    expect(api.submitCalls).toHaveLength(1);
    expect(api.submitCalls[0]).toMatchObject({
      citizenName: 'Pedro Silva',
      citizenEmail: 'pedro@example.test',
      subject: 'Access to the zoology collection',
      consent: true,
      website: '', // honeypot stayed empty
    });
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

function setChecked(root: HTMLElement, selector: string, checked: boolean): void {
  const box = root.querySelector<HTMLInputElement>(selector);
  expect(box).not.toBeNull();
  box!.checked = checked;
  box!.dispatchEvent(new Event('change', { bubbles: true }));
}

function submitForm(root: HTMLElement): void {
  root
    .querySelector<HTMLFormElement>('form')
    ?.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
}
