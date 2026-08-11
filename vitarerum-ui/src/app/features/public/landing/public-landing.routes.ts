import { Routes } from '@angular/router';

import { publicI18nResolver } from '../i18n/public-i18n.resolver';
import { PublicShellComponent } from '../public-shell.component';

/**
 * Public entry point at /public, offering "Ask the Museum" vs "Request an
 * in-situ visit". Additive — /submit-proposal keeps working directly for
 * existing bookmarks/links (see museum-questions-public-page-plan.md).
 */
export const PUBLIC_LANDING_ROUTES: Routes = [
  {
    path: '',
    component: PublicShellComponent,
    resolve: { i18n: publicI18nResolver },
    children: [
      {
        path: '',
        pathMatch: 'full',
        data: { titleKey: 'public.routes.landing' },
        loadComponent: () =>
          import('./public-landing-page.component').then((m) => m.PublicLandingPageComponent),
      },
    ],
  },
];
