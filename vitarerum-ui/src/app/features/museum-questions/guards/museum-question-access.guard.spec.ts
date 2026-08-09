import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter, Route, Router, UrlSegment, UrlTree } from '@angular/router';

import { IDENTITY_SERVICE } from '@core/auth/identity.service';
import { GroupName } from '@core/auth/models/group-name.enum';
import { IdentitySession } from '@core/auth/models/identity-session.model';

import { museumQuestionAccessGuard } from './museum-question-access.guard';

describe('museumQuestionAccessGuard', () => {
  const session = signal<IdentitySession | null>(null);
  let router: Router;

  beforeEach(() => {
    session.set(null);
    TestBed.configureTestingModule({
      providers: [
        provideRouter([]),
        {
          provide: IDENTITY_SERVICE,
          useValue: {
            session: session.asReadonly(),
          },
        },
      ],
    });
    router = TestBed.inject(Router);
  });

  it('allows curatorial and collections management', () => {
    for (const group of ['CURATORIAL', 'COLLECTIONS_MANAGEMENT'] as const) {
      session.set(sessionForGroup(group));
      const result = TestBed.runInInjectionContext(() =>
        museumQuestionAccessGuard({} as Route, [] as UrlSegment[]),
      );
      expect(result).toBe(true);
    }
  });

  it('redirects direction and external users to the dashboard', () => {
    for (const group of ['DIRECTION', 'EXTERNAL'] as const) {
      session.set(sessionForGroup(group));
      const result = TestBed.runInInjectionContext(() =>
        museumQuestionAccessGuard({} as Route, [] as UrlSegment[]),
      );
      expect(router.serializeUrl(result as UrlTree)).toBe('/p/dashboard');
    }
  });
});

function sessionForGroup(group: GroupName): IdentitySession {
  return {
    accessToken: 'token',
    user: { id: 'user-1', email: 'user@example.test', displayName: 'User' },
    group,
    availableGroups: [group],
    permissions: [{ permissionId: `perm-${group}`, group }],
  };
}
