import { Routes } from '@angular/router';

import { staffGuard } from '@core/guards/staff.guard';

export const OBJECTS_ROUTES: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'search' },
  {
    path: 'search',
    title: 'Objects Search',
    canMatch: [staffGuard],
    loadComponent: () =>
      import('./pages/search/object-search-page.component').then(
        (m) => m.ObjectSearchPageComponent,
      ),
  },
];
