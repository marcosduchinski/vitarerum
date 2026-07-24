import { TestBed } from '@angular/core/testing';
import { provideRouter, Route, Router, UrlSegment, UrlTree } from '@angular/router';

import { IDENTITY_SERVICE } from '../auth/identity.service';
import { IdentityServiceMock } from '../auth/identity.service.mock';
import { sysAdminGuard } from './sys-admin.guard';

describe('sysAdminGuard', () => {
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
    TestBed.runInInjectionContext(() => sysAdminGuard({} as Route, [] as UrlSegment[]));

  it('allows system administrators', async () => {
    await identity.signIn({ email: 'eve@admin.example.com', password: 'vita2026' });

    expect(runGuard()).toBe(true);
  });

  it('redirects non-admin staff to the dashboard', async () => {
    await identity.signIn({ email: 'bob@collections.example.com', password: 'vita2026' });

    const result = runGuard();

    expect(router.serializeUrl(result as UrlTree)).toBe('/p/dashboard');
  });
});
