import { DOCUMENT } from '@angular/common';
import { inject, Injectable, signal } from '@angular/core';

import {
  interpolate,
  normalizePublicLocale,
  PublicI18nCatalog,
  PublicI18nParams,
  PublicLocale,
  SOURCE_LOCALE,
} from './public-i18n.model';

/** Shared with any future locale preference elsewhere in the app, on purpose. */
const STORAGE_KEY = 'vitarerum.locale';

/**
 * Runtime translation for the public pages.
 *
 * Catalogues are TypeScript modules pulled in with a dynamic `import()`, so they
 * stay out of the initial bundle and there is no network call that can fail —
 * which is why this service needs no hard-coded fallback copy.
 *
 * `providedIn: 'root'` keeps one instance across the three public route trees,
 * but the service is only ever imported by public code, so the bundler leaves it
 * in the lazy public chunk and the authenticated app never pays for it.
 */
@Injectable({ providedIn: 'root' })
export class PublicI18nService {
  private readonly document = inject(DOCUMENT);

  private readonly localeSignal = signal<PublicLocale>(SOURCE_LOCALE);
  private readonly catalogs = signal<Partial<Record<PublicLocale, PublicI18nCatalog>>>({});
  private initialized = false;

  readonly locale = this.localeSignal.asReadonly();

  /**
   * Resolves the starting locale and loads its catalogue. Idempotent: the route
   * resolver calls it on every navigation into a public route.
   */
  async init(): Promise<void> {
    if (this.initialized) return;
    this.initialized = true;
    await this.apply(this.resolveInitialLocale(), false);
  }

  /** Switches language and remembers the choice for the next visit. */
  async setLocale(locale: PublicLocale): Promise<void> {
    await this.apply(locale, true);
  }

  /**
   * Translates `key`, falling back to the source catalogue and finally to the
   * key itself, which makes a missing entry obvious rather than invisible.
   */
  t(key: string, params: PublicI18nParams = {}): string {
    const value = this.catalogs()[this.locale()]?.[key] ?? this.catalogs()[SOURCE_LOCALE]?.[key];
    return value === undefined ? key : interpolate(value, params);
  }

  /**
   * Picks `{baseKey}.{one|other|…}` by the active locale's plural rules, with
   * `count` available to the entry. Both current locales only need `one` and
   * `other`, but going through `Intl.PluralRules` means a locale with more
   * categories works by adding entries, not by changing this code.
   */
  tPlural(baseKey: string, count: number, params: PublicI18nParams = {}): string {
    const category = new Intl.PluralRules(this.locale()).select(count);
    const key = `${baseKey}.${category}`;
    const withCount = { ...params, count };
    const value = this.t(key, withCount);
    return value === key ? this.t(`${baseKey}.other`, withCount) : value;
  }

  /** Locale-aware number formatting — Portuguese wants "1,5", not "1.5". */
  formatNumber(value: number, options: Intl.NumberFormatOptions = {}): string {
    return new Intl.NumberFormat(this.locale(), options).format(value);
  }

  /**
   * Formats against the *chosen* locale. Passing `undefined` to `Intl` would
   * follow the browser instead, so switching language would leave dates behind.
   */
  formatDate(value: Date | string | number, options: Intl.DateTimeFormatOptions = {}): string {
    const date = value instanceof Date ? value : new Date(value);
    if (Number.isNaN(date.getTime())) return '';
    return new Intl.DateTimeFormat(this.locale(), options).format(date);
  }

  private async apply(locale: PublicLocale, persist: boolean): Promise<void> {
    await this.load(locale);
    if (locale !== SOURCE_LOCALE) {
      await this.load(SOURCE_LOCALE);
    }
    this.localeSignal.set(locale);
    this.document.documentElement.lang = locale;
    if (persist) {
      localStorage.setItem(STORAGE_KEY, locale);
    }
  }

  private async load(locale: PublicLocale): Promise<void> {
    if (this.catalogs()[locale]) return;
    // Explicit branches, not a computed path: the bundler only follows static
    // specifiers. It currently packs both catalogues into one lazy chunk, which
    // at this size beats fighting it for a per-locale split.
    const catalog =
      locale === 'en'
        ? (await import('./catalogs/en')).EN_CATALOG
        : (await import('./catalogs/pt-PT')).PT_PT_CATALOG;
    this.catalogs.update((current) => ({ ...current, [locale]: catalog }));
  }

  /** An explicit stored choice wins; then the browser; then Portuguese. */
  private resolveInitialLocale(): PublicLocale {
    const stored = normalizePublicLocale(localStorage.getItem(STORAGE_KEY));
    if (stored) return stored;
    const candidates = navigator.languages?.length ? navigator.languages : [navigator.language];
    for (const candidate of candidates) {
      const locale = normalizePublicLocale(candidate);
      if (locale) return locale;
    }
    return SOURCE_LOCALE;
  }
}
