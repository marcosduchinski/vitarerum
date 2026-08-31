import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import {
  ActivatedRouteSnapshot,
  convertToParamMap,
  provideRouter,
  Router,
  UrlTree,
} from '@angular/router';

import { IDENTITY_SERVICE } from '@core/auth/identity.service';

import { directionProposalGuard, standardProposalDetailGuard } from './proposal-direction.guard';

describe('proposal Direction guards', () => {
  const session = signal<{ group: string } | null>({ group: 'DIRECTION' });
  let router: Router;

  beforeEach(() => {
    session.set({ group: 'DIRECTION' });
    TestBed.configureTestingModule({
      providers: [
        provideRouter([]),
        { provide: IDENTITY_SERVICE, useValue: { session: session.asReadonly() } },
      ],
    });
    router = TestBed.inject(Router);
  });

  it('allows only Direction members into the dedicated detail', () => {
    const allowed = TestBed.runInInjectionContext(() =>
      directionProposalGuard({} as ActivatedRouteSnapshot, {} as never),
    );
    expect(allowed).toBe(true);

    session.set({ group: 'CURATORIAL' });
    const redirected = TestBed.runInInjectionContext(() =>
      directionProposalGuard({} as ActivatedRouteSnapshot, {} as never),
    );
    expect(router.serializeUrl(redirected as UrlTree)).toBe(
      '/p/collections/proposals/my-assignments',
    );
  });

  it('redirects Direction members away from the standard detail', () => {
    const route = {
      paramMap: convertToParamMap({ id: 'proposal-1' }),
    } as ActivatedRouteSnapshot;

    const result = TestBed.runInInjectionContext(() =>
      standardProposalDetailGuard(route, {} as never),
    );

    expect(router.serializeUrl(result as UrlTree)).toBe(
      '/p/collections/proposals/my-assignments/proposal-1/direction',
    );
  });
});
