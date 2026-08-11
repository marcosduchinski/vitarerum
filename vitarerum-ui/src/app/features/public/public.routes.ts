import { Routes } from '@angular/router';

import { providePublicSubmission } from '@core/providers/provide-public-submission';

import { publicI18nResolver } from './i18n/public-i18n.resolver';
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
    resolve: { i18n: publicI18nResolver },
    children: [
      {
        path: '',
        pathMatch: 'full',
        data: { titleKey: 'public.routes.submitProposal' },
        loadComponent: () =>
          import('./submit-proposal/public-submit-proposal-page.component').then(
            (m) => m.PublicSubmitProposalPageComponent,
          ),
      },
      {
        path: 'received',
        data: { titleKey: 'public.routes.submissionReceived' },
        loadComponent: () =>
          import('./submit-proposal/public-submission-received-page.component').then(
            (m) => m.PublicSubmissionReceivedPageComponent,
          ),
      },
      {
        path: 'confirm',
        data: { titleKey: 'public.routes.submissionConfirm' },
        loadComponent: () =>
          import('./submit-proposal/public-submission-confirm-page.component').then(
            (m) => m.PublicSubmissionConfirmPageComponent,
          ),
      },
      {
        path: 'edit',
        data: { titleKey: 'public.routes.submissionEdit' },
        loadComponent: () =>
          import('./submit-proposal/public-submission-edit-page.component').then(
            (m) => m.PublicSubmissionEditPageComponent,
          ),
      },
    ],
  },
];
