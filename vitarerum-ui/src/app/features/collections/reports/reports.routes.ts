import { Routes } from '@angular/router';

export const REPORTS_ROUTES: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'visits-in-situ' },
  {
    path: 'visits-in-situ/:projectId/:reportId',
    title: 'In-situ visit report details',
    loadComponent: () =>
      import('./pages/in-situ-visit-detail/in-situ-visit-report-detail-page.component').then(
        (m) => m.InSituVisitReportDetailPageComponent,
      ),
  },
  {
    path: 'visits-in-situ',
    title: 'Visits in situ report',
    loadComponent: () =>
      import('./pages/visits-in-situ/visits-in-situ-report-page.component').then(
        (m) => m.VisitsInSituReportPageComponent,
      ),
  },
];
