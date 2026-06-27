import { TestBed } from '@angular/core/testing';
import {
  ActivatedRouteSnapshot,
  provideRouter,
  Router,
  RouterStateSnapshot,
  UrlTree,
} from '@angular/router';

import { authGuard } from './auth.guard';
import { IDENTITY_SERVICE } from '../auth/identity.service';
import { IdentityServiceMock } from '../auth/identity.service.mock';
import { unauthenticatedGuard } from './unauthenticated.guard';

describe('identity guards', () => {
  let identity: IdentityServiceMock;
  let router: Router;

  beforeEach(() => {
    identity = new IdentityServiceMock();

    TestBed.configureTestingModule({
      providers: [provideRouter([]), { provide: IDENTITY_SERVICE, useValue: identity }],
    });

    router = TestBed.inject(Router);
  });

  it('redirects unauthenticated users from protected routes to login', () => {
    const result = TestBed.runInInjectionContext(() =>
      authGuard({} as ActivatedRouteSnapshot, { url: '/p/dashboard' } as RouterStateSnapshot),
    );

    expect(router.serializeUrl(result as UrlTree)).toBe('/login?returnUrl=%2Fp%2Fdashboard');
  });

  it('allows authenticated users into protected routes', async () => {
    await identity.signIn({ email: 'learner@example.com', password: 'vita2026' });

    const result = TestBed.runInInjectionContext(() =>
      authGuard({} as ActivatedRouteSnapshot, { url: '/p/dashboard' } as RouterStateSnapshot),
    );

    expect(result).toBe(true);
  });

  it('redirects authenticated users away from login', async () => {
    await identity.signIn({ email: 'learner@example.com', password: 'vita2026' });

    const result = TestBed.runInInjectionContext(() =>
      unauthenticatedGuard({} as ActivatedRouteSnapshot, { url: '/login' } as RouterStateSnapshot),
    );

    expect(router.serializeUrl(result as UrlTree)).toBe('/p/dashboard');
  });
});
