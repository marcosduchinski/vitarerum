import { Routes } from '@angular/router';

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
    children: [
      {
        path: '',
        pathMatch: 'full',
        title: 'Vitarerum',
        loadComponent: () =>
          import('./public-landing-page.component').then((m) => m.PublicLandingPageComponent),
      },
    ],
  },
];
