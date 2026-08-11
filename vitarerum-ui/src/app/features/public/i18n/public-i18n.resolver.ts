import { inject } from '@angular/core';
import { ResolveFn } from '@angular/router';

import { PublicI18nService } from './public-i18n.service';

/**
 * Loads the active catalogue before the public shell renders, so no page ever
 * paints raw translation keys. Attach to every route that mounts
 * `PublicShellComponent`.
 */
export const publicI18nResolver: ResolveFn<void> = () => inject(PublicI18nService).init();
