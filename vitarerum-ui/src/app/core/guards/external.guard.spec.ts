import { TestBed } from '@angular/core/testing';
import { provideRouter, Route, Router, UrlSegment, UrlTree } from '@angular/router';

import { IDENTITY_SERVICE } from '../auth/identity.service';
import { IdentityServiceMock } from '../auth/identity.service.mock';
import { externalGuard } from './external.guard';

describe('externalGuard', () => {
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
    TestBed.runInInjectionContext(() => externalGuard({} as Route, [] as UrlSegment[]));

  it('allows external researchers', async () => {
    await identity.signIn({ email: 'alice@ext.example.com', password: 'vita2026' });

    expect(runGuard()).toBe(true);
  });

  it('redirects staff users to the staff proposals landing page', async () => {
    await identity.signIn({ email: 'bob@collections.example.com', password: 'vita2026' });

    const result = runGuard();

    expect(router.serializeUrl(result as UrlTree)).toBe('/p/collections/proposals/new');
  });

  it('redirects when there is no session', () => {
    const result = runGuard();

    expect(router.serializeUrl(result as UrlTree)).toBe('/p/collections/proposals/new');
  });
});
