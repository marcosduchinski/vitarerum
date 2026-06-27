import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';

import { authInterceptor } from './auth.interceptor';
import { IDENTITY_SERVICE, IdentityService } from './identity.service';
import { IdentitySession } from './models/identity-session.model';

function createIdentity(session: IdentitySession | null): IdentityService {
  const state = signal<IdentitySession | null>(session);
  return {
    session: state.asReadonly(),
    isAuthenticated: signal(session !== null).asReadonly(),
    isStaff: signal(session !== null && session.group !== 'EXTERNAL').asReadonly(),
    signIn: () => Promise.resolve(),
    signOut: () => state.set(null),
    getAccessToken: () => state()?.accessToken ?? null,
    getPermissionId: () => {
      const s = state();
      if (s === null) return null;
      return s.permissions?.find((p) => p.group === s.group)?.permissionId ?? null;
    },
    setGroup: (group) => void group,
    updateAvailableGroups: (groups) => void groups.length,
  };
}

function setup(identity: IdentityService) {
  TestBed.configureTestingModule({
    providers: [
      provideHttpClient(withInterceptors([authInterceptor])),
      provideHttpClientTesting(),
      { provide: IDENTITY_SERVICE, useValue: identity },
    ],
  });
  return {
    http: TestBed.inject(HttpClient),
    httpMock: TestBed.inject(HttpTestingController),
  };
}

describe('authInterceptor', () => {
  it('adds no auth headers when there is no session', () => {
    const { http, httpMock } = setup(createIdentity(null));

    http.get('/api/x').subscribe();
    const req = httpMock.expectOne('/api/x');

    expect(req.request.headers.has('Authorization')).toBe(false);
    expect(req.request.headers.has('X-Permission-Id')).toBe(false);
    req.flush({});
    httpMock.verify();
  });

  it('adds Authorization and X-Permission-Id for the active group', () => {
    const session: IdentitySession = {
      accessToken: 'jwt',
      user: { id: 'u-1', email: 'a@b.com', displayName: 'A' },
      group: 'CURATORIAL',
      availableGroups: ['CURATORIAL'],
      permissions: [{ permissionId: 'perm-curatorial', group: 'CURATORIAL' }],
    };
    const { http, httpMock } = setup(createIdentity(session));

    http.get('/api/x').subscribe();
    const req = httpMock.expectOne('/api/x');

    expect(req.request.headers.get('Authorization')).toBe('Bearer jwt');
    expect(req.request.headers.get('X-Permission-Id')).toBe('perm-curatorial');
    req.flush({});
    httpMock.verify();
  });
});
