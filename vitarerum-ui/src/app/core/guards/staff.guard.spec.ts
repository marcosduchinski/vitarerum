import { TestBed } from '@angular/core/testing';
import { provideRouter, Route, Router, UrlSegment, UrlTree } from '@angular/router';

import { staffGuard } from './staff.guard';
import { IDENTITY_SERVICE } from '../auth/identity.service';
import { IdentityServiceMock } from '../auth/identity.service.mock';

describe('staffGuard', () => {
  let identity: IdentityServiceMock;
  let router: Router;

  beforeEach(() => {
    identity = new IdentityServiceMock();

    TestBed.configureTestingModule({
      providers: [provideRouter([]), { provide: IDENTITY_SERVICE, useValue: identity }],
    });

    router = TestBed.inject(Router);
  });

  const runGuard = () =>
    TestBed.runInInjectionContext(() => staffGuard({} as Route, [] as UrlSegment[]));

  it('allows users whose active group is a staff group', async () => {
    await identity.signIn({ email: 'bob@collections.example.com', password: 'vita2026' });

    expect(runGuard()).toBe(true);
  });

  it('redirects external users to their proposals home', async () => {
    await identity.signIn({ email: 'alice@ext.example.com', password: 'vita2026' });

    const result = runGuard();

    expect(router.serializeUrl(result as UrlTree)).toBe('/p/collections/proposals/my');
  });

  it('redirects when there is no session', () => {
    const result = runGuard();

    expect(router.serializeUrl(result as UrlTree)).toBe('/p/collections/proposals/my');
  });
});
