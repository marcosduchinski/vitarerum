import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { API_BASE_URL } from '@core/config/app-config.model';

import { IdentityServiceImpl } from './identity.service.impl';
import { IdentitySession } from './models/identity-session.model';
import { LoginResponse } from './models/login.model';
import { readSession, writeSession } from './session-storage.util';

const BASE_URL = 'http://api.test';

const LOGIN_RESPONSE: LoginResponse = {
  accessToken: 'jwt-token',
  user: { id: 'u-1', email: 'alice@example.com', displayName: 'Alice' },
  permissions: [
    { permissionId: 'perm-1-COLLECTIONS_MANAGEMENT', group: 'COLLECTIONS_MANAGEMENT' },
    { permissionId: 'perm-1-CURATORIAL', group: 'CURATORIAL' },
  ],
};

describe('IdentityServiceImpl', () => {
  let httpMock: HttpTestingController;

  beforeEach(() => {
    localStorage.clear();
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: API_BASE_URL, useValue: BASE_URL },
        IdentityServiceImpl,
      ],
    });
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
    localStorage.clear();
  });

  function signIn(service: IdentityServiceImpl): Promise<void> {
    const promise = service.signIn({ email: 'alice@example.com', password: 'secret' });
    const req = httpMock.expectOne(`${BASE_URL}/auth/login`);
    expect(req.request.method).toBe('POST');
    req.flush(LOGIN_RESPONSE);
    return promise;
  }

  it('signs in via POST /auth/login and populates the session', async () => {
    const service = TestBed.inject(IdentityServiceImpl);

    const promise = service.signIn({ email: 'alice@example.com', password: 'secret' });
    const req = httpMock.expectOne(`${BASE_URL}/auth/login`);
    expect(req.request.body).toEqual({ email: 'alice@example.com', password: 'secret' });
    req.flush(LOGIN_RESPONSE);
    await promise;

    expect(service.isAuthenticated()).toBe(true);
    expect(service.getAccessToken()).toBe('jwt-token');
    expect(service.session()?.availableGroups).toEqual(['COLLECTIONS_MANAGEMENT', 'CURATORIAL']);
    expect(service.session()?.group).toBe('COLLECTIONS_MANAGEMENT');
    expect(service.getPermissionId()).toBe('perm-1-COLLECTIONS_MANAGEMENT');
  });

  it('returns the active group permission id and follows group switches', async () => {
    const service = TestBed.inject(IdentityServiceImpl);
    await signIn(service);

    expect(service.getPermissionId()).toBe('perm-1-COLLECTIONS_MANAGEMENT');

    service.setGroup('CURATORIAL');
    expect(service.getPermissionId()).toBe('perm-1-CURATORIAL');

    // A group outside availableGroups is ignored.
    service.setGroup('SYS_ADMIN');
    expect(service.session()?.group).toBe('CURATORIAL');
  });

  it('persists the session to storage and rehydrates a fresh instance', () => {
    const session: IdentitySession = {
      accessToken: 'jwt-token',
      user: { id: 'u-1', email: 'alice@example.com', displayName: 'Alice' },
      group: 'CURATORIAL',
      availableGroups: ['CURATORIAL'],
      permissions: [{ permissionId: 'perm-x', group: 'CURATORIAL' }],
    };
    writeSession(session);

    // Constructed lazily here, so it reads the seeded session on creation.
    const service = TestBed.inject(IdentityServiceImpl);

    expect(service.isAuthenticated()).toBe(true);
    expect(service.getAccessToken()).toBe('jwt-token');
    expect(service.getPermissionId()).toBe('perm-x');
  });

  it('clears the persisted session on sign out', async () => {
    const service = TestBed.inject(IdentityServiceImpl);
    await signIn(service);
    expect(readSession()).not.toBeNull();

    service.signOut();

    expect(service.session()).toBeNull();
    expect(readSession()).toBeNull();
  });
});
