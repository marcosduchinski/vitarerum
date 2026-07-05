import { TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { of } from 'rxjs';

import { TURNSTILE_SITE_KEY } from '@core/config/app-config.model';

import { MuseumQuestionSubmission } from '../models/museum-question.model';
import { MUSEUM_QUESTION_API_SERVICE } from '../services/museum-question-api.service';
import { AskMuseumPageComponent } from './ask-museum-page.component';

class MuseumQuestionApiStub {
  readonly submitCalls: MuseumQuestionSubmission[] = [];

  submit(submission: MuseumQuestionSubmission) {
    this.submitCalls.push(submission);
    return of({ status: 'RECEIVED' as const, email: submission.requesterEmail });
  }
}

describe('AskMuseumPageComponent', () => {
  let api: MuseumQuestionApiStub;
  let router: Router;

  async function setup(siteKey = ''): Promise<void> {
    api = new MuseumQuestionApiStub();

    await TestBed.configureTestingModule({
      imports: [AskMuseumPageComponent],
      providers: [
        provideRouter([]),
        { provide: MUSEUM_QUESTION_API_SERVICE, useValue: api },
        { provide: TURNSTILE_SITE_KEY, useValue: siteKey },
      ],
    }).compileComponents();

    router = TestBed.inject(Router);
    vi.spyOn(router, 'navigate').mockResolvedValue(true);
  }

  it('shows the scope alert', async () => {
    await setup();
    const fixture = TestBed.createComponent(AskMuseumPageComponent);
    fixture.detectChanges();

    expect(
      (fixture.nativeElement as HTMLElement).querySelector('.scope-alert')?.textContent,
    ).toContain('only available for questions related to the use of collections');
  });

  it('hides the captcha when no site key is configured', async () => {
    await setup('');
    const fixture = TestBed.createComponent(AskMuseumPageComponent);
    fixture.detectChanges();

    expect((fixture.nativeElement as HTMLElement).querySelector('app-turnstile')).toBeNull();
  });

  it('submits the question and routes to the received screen', async () => {
    await setup('');
    const fixture = TestBed.createComponent(AskMuseumPageComponent);
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    setInputValue(compiled, '#name', 'Ana Souza');
    setInputValue(compiled, '#email', 'ana@example.test');
    setInputValue(compiled, '#subject', 'Duvida sobre visita in situ');
    setInputValue(compiled, '#message', 'Gostaria de agendar uma visita para pesquisa.');
    setChecked(compiled, '.consent input[type="checkbox"]', true);

    submitForm(compiled);
    fixture.detectChanges();
    await fixture.whenStable();

    expect(api.submitCalls).toHaveLength(1);
    expect(api.submitCalls[0]).toMatchObject({
      requesterName: 'Ana Souza',
      requesterEmail: 'ana@example.test',
      subject: 'Duvida sobre visita in situ',
      message: 'Gostaria de agendar uma visita para pesquisa.',
      consent: true,
      website: '', // honeypot stayed empty
    });
    expect(router.navigate).toHaveBeenCalledWith(['/ask-museum/received'], {
      queryParams: { email: 'ana@example.test' },
    });
  });

  it('blocks submission until consent is given', async () => {
    await setup();
    const fixture = TestBed.createComponent(AskMuseumPageComponent);
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    setInputValue(compiled, '#name', 'Ana Souza');
    setInputValue(compiled, '#email', 'ana@example.test');
    setInputValue(compiled, '#subject', 'Subject');
    setInputValue(compiled, '#message', 'Message body.');
    // consent intentionally left unchecked

    submitForm(compiled);
    fixture.detectChanges();

    expect(api.submitCalls).toHaveLength(0);
    expect(compiled.textContent).toContain('Consent is required to submit.');
  });

  it('rejects an invalid e-mail address', async () => {
    await setup();
    const fixture = TestBed.createComponent(AskMuseumPageComponent);
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    setInputValue(compiled, '#name', 'Ana Souza');
    setInputValue(compiled, '#email', 'not-an-email');
    setInputValue(compiled, '#subject', 'Subject');
    setInputValue(compiled, '#message', 'Message body.');
    setChecked(compiled, '.consent input[type="checkbox"]', true);

    submitForm(compiled);
    fixture.detectChanges();

    expect(api.submitCalls).toHaveLength(0);
    expect(compiled.textContent).toContain('A valid e-mail address is required.');
  });

  it('blocks submission until name/subject/message are filled', async () => {
    await setup();
    const fixture = TestBed.createComponent(AskMuseumPageComponent);
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;

    submitForm(compiled);
    fixture.detectChanges();

    expect(api.submitCalls).toHaveLength(0);
    expect(compiled.textContent).toContain('Your name is required.');
    expect(compiled.textContent).toContain('Subject is required.');
    expect(compiled.textContent).toContain('Your question is required.');
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
