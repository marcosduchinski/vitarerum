import { PublicI18nCatalog, PUBLIC_LOCALES, SOURCE_LOCALE } from '../public-i18n.model';
import { EN_CATALOG } from './en';
import { PT_PT_CATALOG } from './pt-PT';

const CATALOGS: Record<string, PublicI18nCatalog> = {
  'pt-PT': PT_PT_CATALOG,
  en: EN_CATALOG,
};

/** `{{ name }}` placeholders a catalogue entry expects, order-independent. */
function placeholders(value: string): string[] {
  return [...value.matchAll(/\{\{\s*([\w.-]+)\s*\}\}/g)].map((match) => match[1]).sort();
}

describe('public i18n catalogues', () => {
  it('covers every supported locale', () => {
    expect(Object.keys(CATALOGS).sort()).toEqual([...PUBLIC_LOCALES].sort());
  });

  it('defines exactly the same keys in every locale', () => {
    const source = Object.keys(PT_PT_CATALOG).sort();

    for (const [locale, catalog] of Object.entries(CATALOGS)) {
      const keys = Object.keys(catalog).sort();
      expect({ locale, missing: source.filter((key) => !keys.includes(key)) }).toEqual({
        locale,
        missing: [],
      });
      expect({ locale, extra: keys.filter((key) => !source.includes(key)) }).toEqual({
        locale,
        extra: [],
      });
    }
  });

  it('has no empty entries', () => {
    for (const [locale, catalog] of Object.entries(CATALOGS)) {
      const empty = Object.entries(catalog)
        .filter(([, value]) => !value.trim())
        .map(([key]) => key);
      expect({ locale, empty }).toEqual({ locale, empty: [] });
    }
  });

  it('keeps the same placeholders in every translation', () => {
    // Dropping a `{{ name }}` in translation is silent at runtime — the
    // sentence just loses the value — so it is worth failing the build over.
    for (const [locale, catalog] of Object.entries(CATALOGS)) {
      if (locale === SOURCE_LOCALE) continue;

      const mismatched = Object.entries(PT_PT_CATALOG as PublicI18nCatalog)
        .filter(([key, sourceValue]) => {
          const translated = catalog[key];
          return (
            translated !== undefined &&
            placeholders(sourceValue).join() !== placeholders(translated).join()
          );
        })
        .map(([key]) => key);

      expect({ locale, mismatched }).toEqual({ locale, mismatched: [] });
    }
  });

  it('gives every pluralised entry at least a one and an other form', () => {
    for (const [locale, catalog] of Object.entries(CATALOGS)) {
      const bases = new Set(
        Object.keys(catalog)
          .filter((key) => key.endsWith('.one') || key.endsWith('.other'))
          .map((key) => key.replace(/\.(one|other)$/, '')),
      );
      const incomplete = [...bases].filter(
        (base) => !catalog[`${base}.one`] || !catalog[`${base}.other`],
      );
      expect({ locale, incomplete }).toEqual({ locale, incomplete: [] });
    }
  });
});
