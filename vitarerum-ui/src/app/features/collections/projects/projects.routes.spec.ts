import { PROJECTS_ROUTES } from './projects.routes';
import { projectLogAccessGuard } from './guards/project-log-access.guard';
import { ProjectCollectionsDetailPageComponent } from './pages/collections-detail/project-collections-detail-page.component';
import { ProjectCuratorialDetailPageComponent } from './pages/curatorial-detail/project-curatorial-detail-page.component';
import { ProjectDirectionDetailPageComponent } from './pages/direction-detail/project-direction-detail-page.component';

describe('PROJECTS_ROUTES', () => {
  it('routes my projects to a page component', () => {
    const route = PROJECTS_ROUTES.find((candidate) => candidate.path === 'my');

    expect(route?.redirectTo).toBeUndefined();
    expect(route?.loadComponent).toBeDefined();
  });

  it('routes in progress projects to a page component', () => {
    const route = PROJECTS_ROUTES.find((candidate) => candidate.path === 'in-progress');

    expect(route?.redirectTo).toBeUndefined();
    expect(route?.loadComponent).toBeDefined();
  });

  it('routes completed projects to a page component', () => {
    const route = PROJECTS_ROUTES.find((candidate) => candidate.path === 'completed');

    expect(route?.redirectTo).toBeUndefined();
    expect(route?.loadComponent).toBeDefined();
  });

  it('keeps project log routes before the generic detail route', () => {
    const paths = PROJECTS_ROUTES.map((route) => route.path);
    const detailIndex = paths.indexOf(':id');

    expect(paths.indexOf(':id/log/research')).toBeLessThan(detailIndex);
    expect(paths.indexOf(':id/log/exhibition')).toBeLessThan(detailIndex);
    expect(paths.indexOf(':id/log/other')).toBeLessThan(detailIndex);
    expect(paths.indexOf(':id/occurrences/research')).toBeLessThan(detailIndex);
    expect(paths.indexOf(':id/occurrences/exhibition')).toBeLessThan(detailIndex);
    expect(paths.indexOf(':id/occurrences/other')).toBeLessThan(detailIndex);
    expect(paths.indexOf('collections/:id')).toBeLessThan(detailIndex);
    expect(paths.indexOf('curatorial/:id')).toBeLessThan(detailIndex);
    expect(paths.indexOf('direction/:id')).toBeLessThan(detailIndex);
  });

  it('routes staff detail aliases to role-specific page components', async () => {
    const aliases = [
      { path: 'collections/:id', component: ProjectCollectionsDetailPageComponent },
      { path: 'curatorial/:id', component: ProjectCuratorialDetailPageComponent },
      { path: 'direction/:id', component: ProjectDirectionDetailPageComponent },
    ];

    for (const alias of aliases) {
      const route = PROJECTS_ROUTES.find((candidate) => candidate.path === alias.path);
      const component = await route?.loadComponent?.();

      expect(route?.redirectTo).toBeUndefined();
      expect(component).toBe(alias.component);
    }
  });

  it('guards and lazy-loads occurrence log routes separately from access log routes', () => {
    const occurrencePaths = [
      ':id/occurrences/research',
      ':id/occurrences/exhibition',
      ':id/occurrences/other',
    ];

    for (const path of occurrencePaths) {
      const route = PROJECTS_ROUTES.find((candidate) => candidate.path === path);

      expect(route?.loadComponent).toBeDefined();
      expect(route?.canActivate).toContain(projectLogAccessGuard);
    }
  });
});
