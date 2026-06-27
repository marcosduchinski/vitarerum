import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { Router } from '@angular/router';
import { provideRouter } from '@angular/router';

import { provideIdentity } from '@core/providers/provide-identity';
import { USE_MOCK_API, USE_MOCK_AUTH } from '@core/config/app-config.model';
import { IDENTITY_SERVICE } from './identity.service';
import { sessionExpiredInterceptor } from './session-expired.interceptor';
import { HttpClient } from '@angular/common/http';

describe('sessionExpiredInterceptor', () => {
  let http: HttpClient;
  let httpMock: HttpTestingController;
  let router: Router;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideRouter([]),
        provideHttpClient(withInterceptors([sessionExpiredInterceptor])),
        provideHttpClientTesting(),
        provideIdentity(),
        { provide: USE_MOCK_API, useValue: true },
        { provide: USE_MOCK_AUTH, useValue: true },
      ],
    });

    http = TestBed.inject(HttpClient);
    httpMock = TestBed.inject(HttpTestingController);
    router = TestBed.inject(Router);
  });

  afterEach(() => httpMock.verify());

  it('signs out and navigates to /login on 401', async () => {
    const identity = TestBed.inject(IDENTITY_SERVICE);
    // Sign in first so there is a session to expire
    await identity.signIn({ email: 'alice@example.com', password: 'vita2026' });
    expect(identity.isAuthenticated()).toBe(true);

    const navigateSpy = vi.spyOn(router, 'navigateByUrl').mockResolvedValue(true);

    http.get('/api/proposals').subscribe({ error: (e: unknown) => void e });
    httpMock
      .expectOne('/api/proposals')
      .flush({ message: 'Expired' }, { status: 401, statusText: 'Unauthorized' });

    await Promise.resolve(); // flush microtask queue

    expect(identity.isAuthenticated()).toBe(false);
    expect(navigateSpy).toHaveBeenCalledWith('/login');
  });

  it('passes non-401 errors through without signing out', async () => {
    const identity = TestBed.inject(IDENTITY_SERVICE);
    await identity.signIn({ email: 'alice@example.com', password: 'vita2026' });

    let caughtStatus: number | undefined;
    http.get('/api/proposals').subscribe({
      error: (e: { status: number }) => {
        caughtStatus = e.status;
      },
    });
    httpMock
      .expectOne('/api/proposals')
      .flush({ message: 'Forbidden' }, { status: 403, statusText: 'Forbidden' });

    await Promise.resolve();

    expect(identity.isAuthenticated()).toBe(true);
    expect(caughtStatus).toBe(403);
  });

  it('does not sign out on a 401 from the login endpoint', async () => {
    const identity = TestBed.inject(IDENTITY_SERVICE);
    await identity.signIn({ email: 'alice@example.com', password: 'vita2026' });

    const navigateSpy = vi.spyOn(router, 'navigateByUrl').mockResolvedValue(true);

    http.post('/auth/login', {}).subscribe({ error: (e: unknown) => void e });
    httpMock
      .expectOne('/auth/login')
      .flush({ message: 'Invalid' }, { status: 401, statusText: 'Unauthorized' });

    await Promise.resolve();

    expect(identity.isAuthenticated()).toBe(true);
    expect(navigateSpy).not.toHaveBeenCalled();
  });
});
