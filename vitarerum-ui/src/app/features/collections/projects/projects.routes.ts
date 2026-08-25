import { Routes } from '@angular/router';

import { staffGuard } from '@core/guards/staff.guard';

import { projectExternalDetailGuard } from './guards/project-external-detail.guard';
import { projectLogAccessGuard } from './guards/project-log-access.guard';
import { projectPublicationAccessGuard } from './guards/project-publication-access.guard';

export const PROJECTS_ROUTES: Routes = [
  { path: '', pathMatch: 'full', redirectTo: '/p/dashboard' },
  {
    path: 'scientific-return',
    title: 'Scientific Return',
    canMatch: [staffGuard],
    loadComponent: () =>
      import('./pages/scientific-return-queue/scientific-return-queue-page.component').then(
        (m) => m.ScientificReturnQueuePageComponent,
      ),
  },
  {
    path: 'scientific-return-test',
    title: 'Scientific Return Test',
    canMatch: [staffGuard],
    loadComponent: () =>
      import('./pages/scientific-return-test/scientific-return-test-page.component').then(
        (m) => m.ScientificReturnTestPageComponent,
      ),
  },
  {
    path: 'my',
    title: 'My Projects',
    loadComponent: () =>
      import('./pages/my/projects-my-page.component').then((m) => m.ProjectsMyPageComponent),
  },
  {
    path: 'pending',
    title: 'Pending Projects',
    canMatch: [staffGuard],
    loadComponent: () =>
      import('./pages/pending/projects-pending-page.component').then(
        (m) => m.ProjectsPendingPageComponent,
      ),
  },
  {
    path: 'in-progress',
    title: 'In Progress Projects',
    canMatch: [staffGuard],
    loadComponent: () =>
      import('./pages/in-progress/projects-in-progress-page.component').then(
        (m) => m.ProjectsInProgressPageComponent,
      ),
  },
  {
    path: 'completed',
    title: 'Completed Projects',
    canMatch: [staffGuard],
    loadComponent: () =>
      import('./pages/completed/projects-completed-page.component').then(
        (m) => m.ProjectsCompletedPageComponent,
      ),
  },
  {
    path: 'cancelled',
    title: 'Cancelled Projects',
    canMatch: [staffGuard],
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
    path: ':id/follow-up/new',
    title: 'Create Follow-up Project',
    canMatch: [staffGuard],
    loadComponent: () =>
      import('./pages/follow-up/project-follow-up-page.component').then(
        (m) => m.ProjectFollowUpPageComponent,
      ),
  },
  {
    path: 'collections/:id/edit',
    title: 'Edit Project',
    canMatch: [staffGuard],
    loadComponent: () =>
      import('./pages/edit/project-edit-page.component').then((m) => m.ProjectEditPageComponent),
  },
  {
    path: 'collections/:id',
    title: 'Project Detail',
    canMatch: [staffGuard],
    loadComponent: () =>
      import('./pages/collections-detail/project-collections-detail-page.component').then(
        (m) => m.ProjectCollectionsDetailPageComponent,
      ),
  },
  {
    path: 'curatorial/:id/edit',
    title: 'Edit Project',
    canMatch: [staffGuard],
    loadComponent: () =>
      import('./pages/edit/project-edit-page.component').then((m) => m.ProjectEditPageComponent),
  },
  {
    path: 'curatorial/:id',
    title: 'Project Detail',
    canMatch: [staffGuard],
    loadComponent: () =>
      import('./pages/curatorial-detail/project-curatorial-detail-page.component').then(
        (m) => m.ProjectCuratorialDetailPageComponent,
      ),
  },
  {
    path: 'direction/:id/edit',
    title: 'Edit Project',
    canMatch: [staffGuard],
    loadComponent: () =>
      import('./pages/edit/project-edit-page.component').then((m) => m.ProjectEditPageComponent),
  },
  {
    path: 'direction/:id',
    title: 'Project Detail',
    canMatch: [staffGuard],
    loadComponent: () =>
      import('./pages/direction-detail/project-direction-detail-page.component').then(
        (m) => m.ProjectDirectionDetailPageComponent,
      ),
  },
  {
    path: ':id',
    title: 'Project Detail',
    canMatch: [projectExternalDetailGuard],
    loadComponent: () =>
      import('./pages/detail/project-detail-page.component').then(
        (m) => m.ProjectDetailPageComponent,
      ),
  },
];
