import { Routes } from '@angular/router';
import { sysAdminGuard } from '@core/guards/sys-admin.guard';

export const ADMIN_ROUTES: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'users' },
  {
    path: 'users',
    title: 'Users',
    loadComponent: () => import('./users/users-page.component').then((m) => m.UsersPageComponent),
  },
  {
    path: 'users/new',
    title: 'New user',
    loadComponent: () => import('./users/user-new.component').then((m) => m.UserNewComponent),
  },
  {
    path: 'users/:id',
    title: 'User',
    loadComponent: () => import('./users/user-detail.component').then((m) => m.UserDetailComponent),
  },
  {
    path: 'groups',
    title: 'Groups',
    loadComponent: () =>
      import('./groups/groups-page.component').then((m) => m.GroupsPageComponent),
  },
  {
    path: 'groups/:id',
    title: 'Group',
    loadComponent: () =>
      import('./groups/group-detail.component').then((m) => m.GroupDetailComponent),
  },
  {
    path: 'institutions',
    title: 'Institutions',
    loadComponent: () =>
      import('./institutions/institutions-page.component').then((m) => m.InstitutionsPageComponent),
  },
  {
    path: 'document-templates',
    title: 'Document templates',
    loadComponent: () =>
      import('./document-templates/document-templates-page.component').then(
        (m) => m.DocumentTemplatesPageComponent,
      ),
  },
  {
    path: 'collection-data-sources',
    title: 'Collection Data Sources',
    loadComponent: () =>
      import('./collection-data-sources/collection-data-sources-page.component').then(
        (m) => m.CollectionDataSourcesPageComponent,
      ),
  },
  {
    path: 'reference-number-policies',
    title: 'Reference number masks',
    canMatch: [sysAdminGuard],
    loadComponent: () =>
      import('./reference-number-policies/reference-number-policies-page.component').then(
        (m) => m.ReferenceNumberPoliciesPageComponent,
      ),
  },
  {
    path: 'external-publications',
    title: 'External Resource Access',
    canMatch: [sysAdminGuard],
    loadComponent: () =>
      import('./external-publications/external-publications-page.component').then(
        (m) => m.ExternalPublicationsPageComponent,
      ),
  },
  {
    path: 'institutions/new',
    title: 'New institution',
    loadComponent: () =>
      import('./institutions/institution-detail.component').then(
        (m) => m.InstitutionDetailComponent,
      ),
  },
  {
    path: 'institutions/:id',
    title: 'Institution',
    loadComponent: () =>
      import('./institutions/institution-detail.component').then(
        (m) => m.InstitutionDetailComponent,
      ),
  },
];
