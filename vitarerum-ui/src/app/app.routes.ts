import { Routes } from '@angular/router';
import { authGuard } from '@core/guards/auth.guard';
import { unauthenticatedGuard } from '@core/guards/unauthenticated.guard';

export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'login' },
  {
    path: 'login',
    title: 'Login',
    canActivate: [unauthenticatedGuard],
    loadComponent: () =>
      import('@features/auth/login/login.component').then((m) => m.LoginComponent),
  },
  {
    // Public, unauthenticated proposal submission for any citizen — no authGuard.
    path: 'submit-proposal',
    loadChildren: () => import('@features/public/public.routes').then((m) => m.PUBLIC_ROUTES),
  },
  {
    // Public entry point offering "Ask the Museum" vs "Request an in-situ
    // visit" — additive, /submit-proposal keeps working directly (see
    // docs/plans/museum-questions-public-page-plan.md).
    path: 'public',
    loadChildren: () =>
      import('@features/public/landing/public-landing.routes').then((m) => m.PUBLIC_LANDING_ROUTES),
  },
  {
    // Public, unauthenticated "Pergunte ao Museu" question submission — no authGuard.
    path: 'ask-museum',
    loadChildren: () =>
      import('@features/public/ask-museum/ask-museum.routes').then((m) => m.ASK_MUSEUM_ROUTES),
  },
  {
    path: 'p',
    title: 'Vitarerum',
    canActivate: [authGuard],
    loadComponent: () =>
      import('@layout/shell/app-shell.component').then((m) => m.AppShellComponent),
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'dashboard' },
      {
        path: 'dashboard',
        title: 'Dashboard',
        loadComponent: () =>
          import('@features/dashboard/dashboard.component').then((m) => m.DashboardComponent),
      },

      {
        path: 'collections',
        children: [
          {
            path: 'proposals',
            loadChildren: () =>
              import('./features/collections/proposals/proposals.routes').then(
                (m) => m.PROPOSALS_ROUTES,
              ),
          },
          {
            path: 'projects',
            loadChildren: () =>
              import('./features/collections/projects/projects.routes').then(
                (m) => m.PROJECTS_ROUTES,
              ),
          },
          {
            path: 'reports',
            loadChildren: () =>
              import('./features/collections/reports/reports.routes').then((m) => m.REPORTS_ROUTES),
          },
        ],
      },
      // Backward-compat shims so old bookmarks and menus still resolve
      { path: 'proposals', redirectTo: 'collections/proposals', pathMatch: 'prefix' },
      { path: 'projects', redirectTo: 'collections/projects', pathMatch: 'prefix' },

      {
        path: 'objects',
        loadChildren: () =>
          import('./features/objects/objects.routes').then((m) => m.OBJECTS_ROUTES),
      },

      {
        path: 'museum-questions',
        loadChildren: () =>
          import('./features/museum-questions/museum-questions.routes').then(
            (m) => m.MUSEUM_QUESTIONS_ROUTES,
          ),
      },

      {
        path: 'admin',
        loadChildren: () => import('@features/admin/admin.routes').then((m) => m.ADMIN_ROUTES),
      },
    ],
  },
  {
    path: 'not-found',
    title: 'Not Found',
    loadComponent: () =>
      import('@features/errors/not-found.component').then((m) => m.NotFoundComponent),
  },
  { path: '**', redirectTo: 'not-found' },
];
