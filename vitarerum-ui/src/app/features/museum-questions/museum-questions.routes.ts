import { Routes } from '@angular/router';

import { staffGuard } from '@core/guards/staff.guard';

export const MUSEUM_QUESTIONS_ROUTES: Routes = [
  {
    path: '',
    title: 'Museum Questions',
    canMatch: [staffGuard],
    loadComponent: () =>
      import('./pages/museum-questions-page.component').then(
        (m) => m.MuseumQuestionsPageComponent,
      ),
  },
];
