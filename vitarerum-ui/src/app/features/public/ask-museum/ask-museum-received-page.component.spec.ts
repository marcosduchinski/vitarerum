import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { providePublicI18nTesting } from '../i18n/public-i18n.testing';
import { AskMuseumReceivedPageComponent } from './ask-museum-received-page.component';

const CATALOG = {
  'public.askMuseum.received.title': 'Pergunta recebida',
  'public.askMuseum.received.message':
    'Obrigado pela sua pergunta. Recebemo-la e responderemos logo que possível.',
  'public.askMuseum.received.messageTo':
    'Obrigado pela sua pergunta. Recebemo-la e responderemos para {{email}} logo que possível.',
};

async function page(email?: string) {
  await TestBed.configureTestingModule({
    imports: [AskMuseumReceivedPageComponent],
    providers: [provideRouter([]), providePublicI18nTesting('pt-PT', CATALOG)],
  }).compileComponents();

  const fixture = TestBed.createComponent(AskMuseumReceivedPageComponent);
  if (email !== undefined) fixture.componentRef.setInput('email', email);
  fixture.detectChanges();
  return fixture.nativeElement as HTMLElement;
}

describe('AskMuseumReceivedPageComponent', () => {
  it('shows the confirmation message with the submitted e-mail', async () => {
    const compiled = await page('ana@example.test');

    expect(compiled.textContent).toContain('responderemos para ana@example.test');
  });

  it('renders without an e-mail too', async () => {
    const compiled = await page();

    expect(compiled.textContent).toContain('Pergunta recebida');
    expect(compiled.textContent).toContain('responderemos logo que possível');
  });
});
