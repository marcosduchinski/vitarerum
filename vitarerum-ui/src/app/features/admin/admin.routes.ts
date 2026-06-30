import { Routes } from '@angular/router';

export const ADMIN_ROUTES: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'users' },
  {
    path: 'users',
    title: 'Users',
    loadComponent: () =>
      import('./users/users-page.component').then(m => m.UsersPageComponent),
  },
  {
    path: 'users/new',
    title: 'New user',
    loadComponent: () =>
      import('./users/user-new.component').then(m => m.UserNewComponent),
  },
  {
    path: 'users/:id',
    title: 'User',
    loadComponent: () =>
      import('./users/user-detail.component').then(m => m.UserDetailComponent),
  },
  {
    path: 'groups',
    title: 'Groups',
    loadComponent: () =>
      import('./groups/groups-page.component').then(m => m.GroupsPageComponent),
  },
  {
    path: 'groups/:id',
    title: 'Group',
    loadComponent: () =>
      import('./groups/group-detail.component').then(m => m.GroupDetailComponent),
  },
  {
    path: 'institutions',
    title: 'Institutions',
    loadComponent: () =>
      import('./institutions/institutions-page.component').then(
        m => m.InstitutionsPageComponent,
      ),
  },
  {
    path: 'institutions/new',
    title: 'New institution',
    loadComponent: () =>
      import('./institutions/institution-detail.component').then(
        m => m.InstitutionDetailComponent,
      ),
  },
  {
    path: 'institutions/:id',
    title: 'Institution',
    loadComponent: () =>
      import('./institutions/institution-detail.component').then(
        m => m.InstitutionDetailComponent,
      ),
  },
];
