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
];
