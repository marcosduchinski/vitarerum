import { Routes } from '@angular/router';

import { staffGuard } from '@core/guards/staff.guard';

export const MUSEUM_QUESTIONS_ROUTES: Routes = [
  {
    path: '',
    pathMatch: 'full',
    title: 'Museum Questions',
    canMatch: [staffGuard],
    loadComponent: () =>
      import('./pages/museum-questions-page.component').then((m) => m.MuseumQuestionsPageComponent),
  },
  {
    path: ':id',
    title: 'Museum Question',
    canMatch: [staffGuard],
    loadComponent: () =>
      import('./pages/detail/museum-question-detail-page.component').then(
        (m) => m.MuseumQuestionDetailPageComponent,
      ),
  },
];
