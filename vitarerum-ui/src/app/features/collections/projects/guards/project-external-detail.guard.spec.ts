import { TestBed } from '@angular/core/testing';
import { provideRouter, Route, Router, UrlSegment, UrlTree } from '@angular/router';

import { IDENTITY_SERVICE } from '@core/auth/identity.service';
import { IdentityServiceMock } from '@core/auth/identity.service.mock';
import { projectExternalDetailGuard } from './project-external-detail.guard';

describe('projectExternalDetailGuard', () => {
  let identity: IdentityServiceMock;
  let router: Router;

  beforeEach(() => {
    identity = new IdentityServiceMock();

    TestBed.configureTestingModule({
      providers: [provideRouter([]), { provide: IDENTITY_SERVICE, useValue: identity }],
    });

    router = TestBed.inject(Router);
  });

  const runGuard = (projectId = 'project-1') =>
    TestBed.runInInjectionContext(() =>
      projectExternalDetailGuard({} as Route, [new UrlSegment(projectId, {})]),
    );

  it('allows authenticated external users', async () => {
    await identity.signIn({ email: 'alice@ext.example.com', password: 'vita2026' });

    expect(runGuard()).toBe(true);
  });

  it('redirects collections staff to the staff project detail route', async () => {
    await identity.signIn({ email: 'bob@collections.example.com', password: 'vita2026' });

    const result = runGuard('project-42');

    expect(router.serializeUrl(result as UrlTree)).toBe(
      '/p/collections/projects/collections/project-42',
    );
  });

  it('redirects curatorial staff to the curatorial project detail route', async () => {
    await identity.signIn({ email: 'carol@curatorial.example.com', password: 'vita2026' });

    const result = runGuard('project-42');

    expect(router.serializeUrl(result as UrlTree)).toBe(
      '/p/collections/projects/curatorial/project-42',
    );
  });

  it('redirects direction staff to the direction project detail route', async () => {
    await identity.signIn({ email: 'dan@direction.example.com', password: 'vita2026' });

    const result = runGuard('project-42');

    expect(router.serializeUrl(result as UrlTree)).toBe(
      '/p/collections/projects/direction/project-42',
    );
  });

  it('redirects system administrators to the collections staff detail route', async () => {
    await identity.signIn({ email: 'eve@admin.example.com', password: 'vita2026' });

    const result = runGuard('project-42');

    expect(router.serializeUrl(result as UrlTree)).toBe(
      '/p/collections/projects/collections/project-42',
    );
  });

  it('redirects missing sessions away from the external project detail route', () => {
    const result = runGuard('project-42');

    expect(router.serializeUrl(result as UrlTree)).toBe('/p/dashboard');
  });
});
