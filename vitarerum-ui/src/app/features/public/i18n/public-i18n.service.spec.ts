import { TestBed } from '@angular/core/testing';

import { interpolate, normalizePublicLocale } from './public-i18n.model';
import { PublicI18nService } from './public-i18n.service';

/** Pins the browser languages so the default-resolution tests are not
 * at the mercy of whatever the test environment reports. */
function browserLanguages(...languages: string[]): void {
  vi.spyOn(navigator, 'languages', 'get').mockReturnValue(languages);
}

function service(): PublicI18nService {
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({});
  return TestBed.inject(PublicI18nService);
}

describe('normalizePublicLocale', () => {
  it('folds every Portuguese variant onto pt-PT', () => {
    expect(normalizePublicLocale('pt')).toBe('pt-PT');
    expect(normalizePublicLocale('pt-BR')).toBe('pt-PT');
    expect(normalizePublicLocale('pt_PT')).toBe('pt-PT');
  });

  it('folds every English variant onto en', () => {
    expect(normalizePublicLocale('en')).toBe('en');
    expect(normalizePublicLocale('en-GB')).toBe('en');
  });

  it('rejects unsupported and empty tags', () => {
    expect(normalizePublicLocale('fr-FR')).toBeNull();
    expect(normalizePublicLocale('')).toBeNull();
    expect(normalizePublicLocale(null)).toBeNull();
  });
});

describe('interpolate', () => {
  it('substitutes named parameters', () => {
    expect(interpolate('{{ count }} de {{ total }}', { count: 2, total: 5 })).toBe('2 de 5');
  });

  it('leaves a placeholder written when no parameter matches it', () => {
    expect(interpolate('{{ missing }}', {})).toBe('{{ missing }}');
  });
});

describe('PublicI18nService', () => {
  afterEach(() => vi.restoreAllMocks());

  it('starts in Portuguese when the browser asks for an unsupported language', async () => {
    browserLanguages('fr-FR');
    const i18n = service();

    await i18n.init();

    expect(i18n.locale()).toBe('pt-PT');
    expect(i18n.t('public.shell.language')).toBe('Idioma');
  });

  it('follows the browser when it asks for a language we support', async () => {
    browserLanguages('en-GB');
    const i18n = service();

    await i18n.init();

    expect(i18n.locale()).toBe('en');
  });

  it('honours a stored choice over the browser language', async () => {
    browserLanguages('pt-PT');
    localStorage.setItem('vitarerum.locale', 'en');
    const i18n = service();

    await i18n.init();

    expect(i18n.locale()).toBe('en');
    expect(i18n.t('public.shell.language')).toBe('Language');
  });

  it('switches language, persists it and updates the document language', async () => {
    browserLanguages('pt-PT');
    const i18n = service();
    await i18n.init();

    await i18n.setLocale('en');

    expect(i18n.locale()).toBe('en');
    expect(i18n.t('public.routes.askMuseum')).toBe('Ask the Museum');
    expect(localStorage.getItem('vitarerum.locale')).toBe('en');
    expect(document.documentElement.lang).toBe('en');
  });

  it('keeps the source catalogue loaded as a fallback for the active locale', async () => {
    browserLanguages('en');
    const i18n = service();
    await i18n.init();

    // Reaching a pt-PT entry while `en` is active proves the fallback chain is
    // wired; a bare key would come back if only the active catalogue loaded.
    expect(i18n.t('public.appName')).toBe('Vitarerum');
  });

  it('returns the key itself when nothing defines it, so gaps are visible', async () => {
    browserLanguages('pt-PT');
    const i18n = service();
    await i18n.init();

    expect(i18n.t('public.does.not.exist')).toBe('public.does.not.exist');
  });

  it('resolves the locale once, however many public routes are entered', async () => {
    browserLanguages('pt-PT');
    const i18n = service();
    await i18n.init();
    await i18n.setLocale('en');

    await i18n.init();

    expect(i18n.locale()).toBe('en');
  });
});
