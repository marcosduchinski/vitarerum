import { Routes } from '@angular/router';

import { museumQuestionAccessGuard } from './guards/museum-question-access.guard';

export const MUSEUM_QUESTIONS_ROUTES: Routes = [
  {
    path: '',
    pathMatch: 'full',
    title: 'All Enquiries',
    data: { museumQuestionListMode: 'all' },
    canMatch: [museumQuestionAccessGuard],
    loadComponent: () =>
      import('./pages/museum-questions-page.component').then((m) => m.MuseumQuestionsPageComponent),
  },
  {
    path: 'new',
    title: 'New Inquiries',
    data: { museumQuestionListMode: 'new' },
    canMatch: [museumQuestionAccessGuard],
    loadComponent: () =>
      import('./pages/museum-questions-page.component').then((m) => m.MuseumQuestionsPageComponent),
  },
  {
    path: 'my',
    title: 'My Enquiries',
    canMatch: [museumQuestionAccessGuard],
    loadComponent: () =>
      import('./pages/my-inquiries/my-inquiries-page.component').then(
        (m) => m.MyInquiriesPageComponent,
      ),
  },
  {
    path: ':id',
    title: 'Public Inquiry',
    canMatch: [museumQuestionAccessGuard],
    loadComponent: () =>
      import('./pages/detail/museum-question-detail-page.component').then(
        (m) => m.MuseumQuestionDetailPageComponent,
      ),
  },
];
