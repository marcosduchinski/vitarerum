import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { providePublicI18nTesting } from '../i18n/public-i18n.testing';
import { PublicLandingPageComponent } from './public-landing-page.component';

const CATALOG = {
  'public.landing.askMuseum.title': 'Pergunte ao Museu',
  'public.landing.submitProposal.title': 'Pedir uma visita in situ',
};

async function page(catalog: Record<string, string> = CATALOG) {
  await TestBed.configureTestingModule({
    imports: [PublicLandingPageComponent],
    providers: [provideRouter([]), providePublicI18nTesting('pt-PT', catalog)],
  }).compileComponents();

  const fixture = TestBed.createComponent(PublicLandingPageComponent);
  fixture.detectChanges();
  await fixture.whenStable();
  return fixture.nativeElement as HTMLElement;
}

describe('PublicLandingPageComponent', () => {
  it('shows both choices linking to their respective flows', async () => {
    const compiled = await page();

    const links = Array.from(compiled.querySelectorAll<HTMLAnchorElement>('a.choice'));
    expect(links).toHaveLength(2);
    expect(links[0].getAttribute('href')).toBe('/ask-museum');
    expect(links[1].getAttribute('href')).toBe('/submit-proposal');
    expect(compiled.textContent).toContain('Pergunte ao Museu');
    expect(compiled.textContent).toContain('Pedir uma visita in situ');
  });

  it('takes every visible string from the catalogue', async () => {
    // With an empty catalogue the service echoes keys back, so any copy left
    // hardcoded in the template shows up here as prose instead of a key.
    const compiled = await page({});
    const text = (selector: string) =>
      Array.from(compiled.querySelectorAll(selector)).map((el) => el.textContent?.trim());

    expect(text('.page-header__eyebrow')).toEqual(['public.landing.eyebrow']);
    expect(text('.page-header h1')).toEqual(['public.landing.title']);
    expect(text('.page-header__description')).toEqual(['public.landing.description']);
    expect(text('.choice__title')).toEqual([
      'public.landing.askMuseum.title',
      'public.landing.submitProposal.title',
    ]);
    expect(text('.choice__desc')).toEqual([
      'public.landing.askMuseum.description',
      'public.landing.submitProposal.description',
    ]);
  });
});
