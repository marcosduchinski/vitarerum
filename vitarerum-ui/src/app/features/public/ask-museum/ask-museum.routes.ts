import { Routes } from '@angular/router';

import { provideMuseumQuestions } from '@core/providers/provide-museum-questions';

import { publicI18nResolver } from '../i18n/public-i18n.resolver';
import { PublicShellComponent } from '../public-shell.component';

/**
 * Public, unauthenticated "Pergunte ao Museu" question submission. Mounted at
 * /ask-museum with NO authGuard. Providers are scoped here so the real/mock
 * museum-question service is only loaded for this lazy chunk.
 */
export const ASK_MUSEUM_ROUTES: Routes = [
  {
    path: '',
    component: PublicShellComponent,
    providers: [provideMuseumQuestions()],
    resolve: { i18n: publicI18nResolver },
    children: [
      {
        path: '',
        pathMatch: 'full',
        data: { titleKey: 'public.routes.askMuseum' },
        loadComponent: () =>
          import('./ask-museum-page.component').then((m) => m.AskMuseumPageComponent),
      },
      {
        path: 'received',
        data: { titleKey: 'public.routes.askMuseumReceived' },
        loadComponent: () =>
          import('./ask-museum-received-page.component').then(
            (m) => m.AskMuseumReceivedPageComponent,
          ),
      },
    ],
  },
];
