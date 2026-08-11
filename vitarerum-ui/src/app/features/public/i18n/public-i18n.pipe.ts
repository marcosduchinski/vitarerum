import { inject, Pipe, PipeTransform } from '@angular/core';

import { PublicI18nParams } from './public-i18n.model';
import { PublicI18nService } from './public-i18n.service';

/**
 * Translates a key in public templates: `{{ 'public.shell.language' | t }}`.
 *
 * Impure on purpose — the transform reads the locale signal, so switching
 * language repaints every usage without a reload. Public pages are small and
 * static enough that the extra evaluations are not a concern.
 */
@Pipe({
  name: 't',
  standalone: true,
  pure: false,
})
export class PublicI18nPipe implements PipeTransform {
  private readonly i18n = inject(PublicI18nService);

  transform(key: string, params: PublicI18nParams = {}): string {
    return this.i18n.t(key, params);
  }
}
