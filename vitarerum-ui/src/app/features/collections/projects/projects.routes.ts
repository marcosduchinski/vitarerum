import { Routes } from '@angular/router';

import { projectLogAccessGuard } from './guards/project-log-access.guard';
import { projectPublicationAccessGuard } from './guards/project-publication-access.guard';

export const PROJECTS_ROUTES: Routes = [
  { path: '', pathMatch: 'full', redirectTo: '/p/dashboard' },
  {
    path: 'my',
    title: 'My Projects',
    loadComponent: () =>
      import('./pages/my/projects-my-page.component').then((m) => m.ProjectsMyPageComponent),
  },
  {
    path: 'pending',
    title: 'Pending Projects',
    loadComponent: () =>
      import('./pages/pending/projects-pending-page.component').then(
        (m) => m.ProjectsPendingPageComponent,
      ),
  },
  {
    path: 'in-progress',
    title: 'In Progress Projects',
    loadComponent: () =>
      import('./pages/in-progress/projects-in-progress-page.component').then(
        (m) => m.ProjectsInProgressPageComponent,
      ),
  },
  {
    path: 'completed',
    title: 'Completed Projects',
    loadComponent: () =>
      import('./pages/completed/projects-completed-page.component').then(
        (m) => m.ProjectsCompletedPageComponent,
      ),
  },
  {
    path: 'cancelled',
    title: 'Cancelled Projects',
    loadComponent: () =>
      import('./pages/cancelled/projects-cancelled-page.component').then(
        (m) => m.ProjectsCancelledPageComponent,
      ),
  },
  {
    path: ':id/log/research',
    title: 'Research Log',
    canActivate: [projectLogAccessGuard],
    loadComponent: () =>
      import('./pages/log/project-research-log-page.component').then(
        (m) => m.ProjectResearchLogPageComponent,
      ),
  },
  {
    path: ':id/log/exhibition',
    title: 'Exhibition Log',
    canActivate: [projectLogAccessGuard],
    loadComponent: () =>
      import('./pages/log/project-exhibition-log-page.component').then(
        (m) => m.ProjectExhibitionLogPageComponent,
      ),
  },
  {
    path: ':id/log/other',
    title: 'Project Log',
    canActivate: [projectLogAccessGuard],
    loadComponent: () =>
      import('./pages/log/project-other-log-page.component').then(
        (m) => m.ProjectOtherLogPageComponent,
      ),
  },
  {
    path: ':id/occurrences/research',
    title: 'Research Occurrences',
    canActivate: [projectLogAccessGuard],
    loadComponent: () =>
      import('./pages/log/project-research-occurrence-log-page.component').then(
        (m) => m.ProjectResearchOccurrenceLogPageComponent,
      ),
  },
  {
    path: ':id/occurrences/exhibition',
    title: 'Exhibition Occurrences',
    canActivate: [projectLogAccessGuard],
    loadComponent: () =>
      import('./pages/log/project-exhibition-occurrence-log-page.component').then(
        (m) => m.ProjectExhibitionOccurrenceLogPageComponent,
      ),
  },
  {
    path: ':id/occurrences/other',
    title: 'Project Occurrences',
    canActivate: [projectLogAccessGuard],
    loadComponent: () =>
      import('./pages/log/project-other-occurrence-log-page.component').then(
        (m) => m.ProjectOtherOccurrenceLogPageComponent,
      ),
  },
  {
    path: ':id/publications',
    title: 'Publication Log',
    canActivate: [projectPublicationAccessGuard],
    loadComponent: () =>
      import('./pages/log/project-publication-log-page.component').then(
        (m) => m.ProjectPublicationLogPageComponent,
      ),
  },
  {
    path: 'collections/:id',
    title: 'Project Detail',
    loadComponent: () =>
      import('./pages/collections-detail/project-collections-detail-page.component').then(
        (m) => m.ProjectCollectionsDetailPageComponent,
      ),
  },
  {
    path: 'curatorial/:id',
    title: 'Project Detail',
    loadComponent: () =>
      import('./pages/curatorial-detail/project-curatorial-detail-page.component').then(
        (m) => m.ProjectCuratorialDetailPageComponent,
      ),
  },
  {
    path: 'direction/:id',
    title: 'Project Detail',
    loadComponent: () =>
      import('./pages/direction-detail/project-direction-detail-page.component').then(
        (m) => m.ProjectDirectionDetailPageComponent,
      ),
  },
  {
    path: ':id',
    title: 'Project Detail',
    loadComponent: () =>
      import('./pages/detail/project-detail-page.component').then(
        (m) => m.ProjectDetailPageComponent,
      ),
  },
];
