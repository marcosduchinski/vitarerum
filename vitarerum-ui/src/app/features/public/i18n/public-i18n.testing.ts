import { Provider, signal } from '@angular/core';

import { PublicI18nCatalog, PublicI18nParams, PublicLocale } from './public-i18n.model';
import { PublicI18nService } from './public-i18n.service';

/**
 * Replaces {@link PublicI18nService} with an in-memory catalogue, so component
 * tests assert against the keys they care about instead of loading real copy.
 * Unknown keys come back as the key itself, matching the real service.
 */
export function providePublicI18nTesting(
  locale: PublicLocale = 'pt-PT',
  catalog: PublicI18nCatalog = {},
): Provider {
  const localeSignal = signal(locale);
  const t = (key: string, params: PublicI18nParams = {}) =>
    (catalog[key] ?? key).replace(/\{\{\s*([\w.-]+)\s*\}\}/g, (match, name: string) => {
      const param = params[name];
      return param === undefined ? match : String(param);
    });
  return {
    provide: PublicI18nService,
    useValue: {
      locale: localeSignal.asReadonly(),
      init: () => Promise.resolve(),
      setLocale: (next: PublicLocale) => {
        localeSignal.set(next);
        return Promise.resolve();
      },
      t,
      tPlural: (baseKey: string, count: number, params: PublicI18nParams = {}) => {
        const category = new Intl.PluralRules(localeSignal()).select(count);
        const withCount = { ...params, count };
        const key = `${baseKey}.${category}`;
        const value = t(key, withCount);
        return value === key ? t(`${baseKey}.other`, withCount) : value;
      },
      formatNumber: (value: number, options: Intl.NumberFormatOptions = {}) =>
        new Intl.NumberFormat(localeSignal(), options).format(value),
      formatDate: (value: Date | string | number, options: Intl.DateTimeFormatOptions = {}) => {
        const date = value instanceof Date ? value : new Date(value);
        return Number.isNaN(date.getTime())
          ? ''
          : new Intl.DateTimeFormat(localeSignal(), options).format(date);
      },
    } satisfies Partial<PublicI18nService>,
  };
}
