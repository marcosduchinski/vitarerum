import { TestBed } from '@angular/core/testing';
import { ActivatedRouteSnapshot, Router, RouterStateSnapshot, UrlTree } from '@angular/router';
import { of, throwError } from 'rxjs';

import { IDENTITY_SERVICE } from '@core/auth/identity.service';
import { IdentitySession } from '@core/auth/models/identity-session.model';
import { GroupName } from '@core/auth/models/group-name.enum';
import { PROJECT_API_SERVICE } from '../services/project-api.service';
import { projectLogAccessGuard } from './project-log-access.guard';

function makeSession(group: GroupName): IdentitySession {
  return {
    accessToken: 'tok',
    user: { id: 'u-1', email: 'test@example.com', displayName: 'Test' },
    group,
    availableGroups: [group],
  };
}

function makeRoute(projectId: string): ActivatedRouteSnapshot {
  const route = new ActivatedRouteSnapshot();
  (route as unknown as { _paramMap: Map<string, string> })._paramMap = new Map([['id', projectId]]);
  Object.defineProperty(route, 'paramMap', {
    get: () => ({
      get: (key: string) => (key === 'id' ? projectId : null),
    }),
  });
  return route;
}

describe('projectLogAccessGuard', () => {
  let identityService: { session: () => IdentitySession | null };
  let projectService: { getProject: ReturnType<typeof vi.fn> };

  beforeEach(() => {
    projectService = { getProject: vi.fn() };
    identityService = { session: vi.fn() };

    TestBed.configureTestingModule({
      providers: [
        { provide: PROJECT_API_SERVICE, useValue: projectService },
        { provide: IDENTITY_SERVICE, useValue: identityService },
      ],
    });

    void TestBed.inject(Router);
  });

  const runGuard = (route: ActivatedRouteSnapshot) =>
    TestBed.runInInjectionContext(() =>
      projectLogAccessGuard(route, {} as RouterStateSnapshot),
    );

  it('redirects to dashboard when session has no group assigned', async () => {
    (identityService.session as ReturnType<typeof vi.fn>).mockReturnValue({
      accessToken: 'tok',
      user: { id: 'u-1', email: 'test@example.com', displayName: 'Test' },
      group: null,
      availableGroups: [],
    });

    const result = await runGuard(makeRoute('proj-1'));

    expect(result).toBeInstanceOf(UrlTree);
    expect((result as UrlTree).toString()).toContain('/p/dashboard');
    expect(projectService.getProject).not.toHaveBeenCalled();
  });

  it('allows staff through without checking project status', async () => {
    (identityService.session as ReturnType<typeof vi.fn>).mockReturnValue(makeSession('CURATORIAL' as GroupName));

    const result = await runGuard(makeRoute('proj-1'));

    expect(result).toBe(true);
    expect(projectService.getProject).not.toHaveBeenCalled();
  });

  it('allows researcher through when project is IN_PROGRESS', async () => {
    (identityService.session as ReturnType<typeof vi.fn>).mockReturnValue(makeSession('EXTERNAL' as GroupName));
    projectService.getProject.mockReturnValue(of({ status: 'IN_PROGRESS' }));

    const result = await runGuard(makeRoute('proj-1'));

    expect(result).toBe(true);
  });

  it('redirects researcher to project detail when project is CREATED', async () => {
    (identityService.session as ReturnType<typeof vi.fn>).mockReturnValue(makeSession('EXTERNAL' as GroupName));
    projectService.getProject.mockReturnValue(of({ status: 'CREATED' }));

    const result = await runGuard(makeRoute('proj-1'));

    expect(result).toBeInstanceOf(UrlTree);
    expect((result as UrlTree).toString()).toContain('/p/collections/projects/proj-1');
  });

  it('redirects researcher to my projects when project is COMPLETED', async () => {
    (identityService.session as ReturnType<typeof vi.fn>).mockReturnValue(makeSession('EXTERNAL' as GroupName));
    projectService.getProject.mockReturnValue(of({ status: 'COMPLETED' }));

    const result = await runGuard(makeRoute('proj-1'));

    expect(result).toBeInstanceOf(UrlTree);
    expect((result as UrlTree).toString()).toContain('/p/collections/projects/proj-1');
  });

  it('redirects to my projects when project fetch fails', async () => {
    (identityService.session as ReturnType<typeof vi.fn>).mockReturnValue(makeSession('EXTERNAL' as GroupName));
    projectService.getProject.mockReturnValue(throwError(() => ({ status: 404 })));

    const result = await runGuard(makeRoute('proj-1'));

    expect(result).toBeInstanceOf(UrlTree);
    expect((result as UrlTree).toString()).toContain('/p/collections/projects/my');
  });

  it('redirects to my projects when project fetch fails with no id', async () => {
    (identityService.session as ReturnType<typeof vi.fn>).mockReturnValue(makeSession('EXTERNAL' as GroupName));
    projectService.getProject.mockReturnValue(throwError(() => ({ status: 404 })));

    const result = await runGuard(makeRoute('proj-nonexistent'));

    expect(result).toBeInstanceOf(UrlTree);
    expect((result as UrlTree).toString()).toContain('/p/collections/projects/my');
  });
});
