import { TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { of } from 'rxjs';

import { TURNSTILE_SITE_KEY } from '@core/config/app-config.model';

import { providePublicI18nTesting } from '../i18n/public-i18n.testing';
import { MuseumQuestionSubmission } from '../models/museum-question.model';
import { MUSEUM_QUESTION_API_SERVICE } from '../services/museum-question-api.service';
import { AskMuseumPageComponent } from './ask-museum-page.component';

/** Only the entries these tests assert on; anything else echoes its key. */
const CATALOG = {
  'public.askMuseum.scopeNotice':
    'De momento, o Pergunte ao Museu está disponível apenas para perguntas sobre o uso de coleções.',
  'public.askMuseum.form.name.required': 'O seu nome é obrigatório.',
  'public.askMuseum.form.email.invalid': 'É obrigatório um endereço de e-mail válido.',
  'public.askMuseum.form.subject.required': 'O assunto é obrigatório.',
  'public.askMuseum.form.message.required': 'A sua pergunta é obrigatória.',
  'public.askMuseum.form.consent.required': 'É obrigatório dar consentimento para submeter.',
  'public.askMuseum.form.images.tooMany': 'Anexe no máximo {{count}} imagens.',
  'public.askMuseum.form.images.selected.one': '{{count}} imagem selecionada · {{size}} no total',
  'public.askMuseum.form.images.selected.other':
    '{{count}} imagens selecionadas · {{size}} no total',
};

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
        providePublicI18nTesting('pt-PT', CATALOG),
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
    ).toContain('disponível apenas para perguntas sobre o uso de coleções');
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

  it('includes selected image attachments in the submission', async () => {
    await setup('');
    const fixture = TestBed.createComponent(AskMuseumPageComponent);
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    setInputValue(compiled, '#name', 'Ana Souza');
    setInputValue(compiled, '#email', 'ana@example.test');
    setInputValue(compiled, '#subject', 'Duvida sobre visita in situ');
    setInputValue(compiled, '#message', 'Gostaria de agendar uma visita para pesquisa.');
    setChecked(compiled, '.consent input[type="checkbox"]', true);
    setFiles(compiled, '#attachments', [
      new File([new Uint8Array([1, 2, 3])], 'artifact.png', { type: 'image/png' }),
    ]);

    submitForm(compiled);
    fixture.detectChanges();
    await fixture.whenStable();

    expect(api.submitCalls[0].attachments?.map((file) => file.name)).toEqual(['artifact.png']);
  });

  it('blocks submission when more than ten images are selected', async () => {
    await setup();
    const fixture = TestBed.createComponent(AskMuseumPageComponent);
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    setInputValue(compiled, '#name', 'Ana Souza');
    setInputValue(compiled, '#email', 'ana@example.test');
    setInputValue(compiled, '#subject', 'Subject');
    setInputValue(compiled, '#message', 'Message body.');
    setChecked(compiled, '.consent input[type="checkbox"]', true);
    setFiles(
      compiled,
      '#attachments',
      Array.from(
        { length: 11 },
        (_, index) => new File([new Uint8Array([1])], `${index}.png`, { type: 'image/png' }),
      ),
    );

    submitForm(compiled);
    fixture.detectChanges();

    expect(api.submitCalls).toHaveLength(0);
    expect(compiled.textContent).toContain('Anexe no máximo 10 imagens.');
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
    expect(compiled.textContent).toContain('É obrigatório dar consentimento para submeter.');
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
    expect(compiled.textContent).toContain('É obrigatório um endereço de e-mail válido.');
  });

  it('blocks submission until name/subject/message are filled', async () => {
    await setup();
    const fixture = TestBed.createComponent(AskMuseumPageComponent);
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;

    submitForm(compiled);
    fixture.detectChanges();

    expect(api.submitCalls).toHaveLength(0);
    expect(compiled.textContent).toContain('O seu nome é obrigatório.');
    expect(compiled.textContent).toContain('O assunto é obrigatório.');
    expect(compiled.textContent).toContain('A sua pergunta é obrigatória.');
  });

  it('takes every visible string from the catalogue', async () => {
    // Rendered with an empty catalogue, so the service echoes keys back: any
    // copy still hardcoded in the template shows up here as prose.
    await setup('');
    TestBed.resetTestingModule();
    await TestBed.configureTestingModule({
      imports: [AskMuseumPageComponent],
      providers: [
        provideRouter([]),
        { provide: MUSEUM_QUESTION_API_SERVICE, useValue: api },
        { provide: TURNSTILE_SITE_KEY, useValue: '' },
        providePublicI18nTesting('pt-PT', {}),
      ],
    }).compileComponents();
    const fixture = TestBed.createComponent(AskMuseumPageComponent);
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;

    const prose = visibleText(compiled).filter(
      (text) =>
        !text.startsWith('public.askMuseum.') &&
        // Required-field markers and the bot honeypot, neither of which is
        // product copy a citizen reads.
        text !== '*' &&
        text !== 'Website',
    );
    expect(prose).toEqual([]);

    const placeholders = Array.from(
      compiled.querySelectorAll<HTMLInputElement | HTMLTextAreaElement>('[placeholder]'),
    ).map((field) => field.placeholder);
    expect(placeholders.every((value) => value.startsWith('public.askMuseum.'))).toBe(true);
  });

  it('pluralises the attachment hint by the number of images picked', async () => {
    await setup();
    const fixture = TestBed.createComponent(AskMuseumPageComponent);
    fixture.detectChanges();
    const compiled = fixture.nativeElement as HTMLElement;

    // The e-mail field has a hint too, so scope the query to this field.
    const hint = () =>
      compiled.querySelector('#attachments')?.closest('.field')?.querySelector('.field__hint')
        ?.textContent;

    setFiles(compiled, '#attachments', [
      new File([new Uint8Array(1024)], 'a.png', { type: 'image/png' }),
    ]);
    fixture.detectChanges();
    expect(hint()).toContain('1 imagem selecionada');

    setFiles(compiled, '#attachments', [
      new File([new Uint8Array(1024)], 'a.png', { type: 'image/png' }),
      new File([new Uint8Array(1024)], 'b.png', { type: 'image/png' }),
    ]);
    fixture.detectChanges();
    expect(hint()).toContain('2 imagens selecionadas');
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

function setFiles(root: HTMLElement, selector: string, files: readonly File[]): void {
  const input = root.querySelector<HTMLInputElement>(selector);
  expect(input).not.toBeNull();
  Object.defineProperty(input, 'files', {
    configurable: true,
    value: files,
  });
  input!.dispatchEvent(new Event('change', { bubbles: true }));
}

function submitForm(root: HTMLElement): void {
  root
    .querySelector<HTMLFormElement>('form')
    ?.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
}

/** Every non-empty text node rendered, in document order. */
function visibleText(root: HTMLElement): string[] {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const texts: string[] = [];
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const text = node.textContent?.trim();
    if (text) texts.push(text);
  }
  return texts;
}
