import { Routes } from '@angular/router';

import { providePublicSubmission } from '@core/providers/provide-public-submission';

import { PublicShellComponent } from './public-shell.component';

/**
 * Public, unauthenticated proposal submission. Mounted at /submit-proposal with
 * NO authGuard. Providers are scoped here so the real/mock public service is
 * only loaded for this lazy chunk, never the authenticated app.
 */
export const PUBLIC_ROUTES: Routes = [
  {
    path: '',
    component: PublicShellComponent,
    providers: [providePublicSubmission()],
    children: [
      {
        path: '',
        pathMatch: 'full',
        title: 'Submit a proposal',
        loadComponent: () =>
          import('./submit-proposal/public-submit-proposal-page.component').then(
            (m) => m.PublicSubmitProposalPageComponent,
          ),
      },
      {
        path: 'received',
        title: 'Request received',
        loadComponent: () =>
          import('./submit-proposal/public-submission-received-page.component').then(
            (m) => m.PublicSubmissionReceivedPageComponent,
          ),
      },
      {
        path: 'confirm',
        title: 'Confirm your request',
        loadComponent: () =>
          import('./submit-proposal/public-submission-confirm-page.component').then(
            (m) => m.PublicSubmissionConfirmPageComponent,
          ),
      },
    ],
  },
];
