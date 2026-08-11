/**
 * Locale vocabulary for the public (unauthenticated) pages.
 *
 * Deliberately scoped to `features/public`: the authenticated app is not
 * translated and may later adopt a different approach. Nothing outside this
 * folder should import from here.
 */

/** Portuguese is the source language — these pages address citizens in Portugal. */
export type PublicLocale = 'pt-PT' | 'en';

/** Source catalogue and last-resort fallback for keys missing from a translation. */
export const SOURCE_LOCALE: PublicLocale = 'pt-PT';

export const PUBLIC_LOCALES: readonly PublicLocale[] = ['pt-PT', 'en'];

export type PublicI18nParams = Readonly<Record<string, string | number>>;

export type PublicI18nCatalog = Readonly<Record<string, string>>;

export function isPublicLocale(value: string): value is PublicLocale {
  return (PUBLIC_LOCALES as readonly string[]).includes(value);
}

/**
 * Maps a browser/stored language tag onto a supported locale, or `null` when
 * unsupported. Any Portuguese variant (including `pt-BR`) resolves to `pt-PT`.
 */
export function normalizePublicLocale(value: string | null | undefined): PublicLocale | null {
  if (!value) return null;
  const normalized = value.trim().replace('_', '-');
  if (isPublicLocale(normalized)) return normalized;
  const lower = normalized.toLowerCase();
  if (lower === 'pt' || lower.startsWith('pt-')) return 'pt-PT';
  if (lower === 'en' || lower.startsWith('en-')) return 'en';
  return null;
}

/**
 * Substitutes `{{ name }}` placeholders in a catalogue entry. A placeholder with
 * no matching parameter is left as written, so the omission shows up in the UI
 * instead of turning into a blank.
 */
export function interpolate(value: string, params: PublicI18nParams): string {
  return value.replace(/\{\{\s*([\w.-]+)\s*\}\}/g, (match, name: string) => {
    const param = params[name];
    return param === undefined ? match : String(param);
  });
}
