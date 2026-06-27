import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { firstValueFrom } from 'rxjs';

import { API_BASE_URL } from '@core/config/app-config.model';

import { AuthApiService } from './auth-api.service';
import { LoginResponse } from './models/login.model';

const BASE_URL = 'http://api.test';

describe('AuthApiService', () => {
  let service: AuthApiService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: API_BASE_URL, useValue: BASE_URL },
      ],
    });
    service = TestBed.inject(AuthApiService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => httpMock.verify());

  it('POSTs credentials to /auth/login and returns the response', async () => {
    const response: LoginResponse = {
      accessToken: 'jwt',
      user: { id: 'u-1', email: 'a@b.com', displayName: 'A' },
      permissions: [{ permissionId: 'perm-1', group: 'EXTERNAL' }],
    };

    const promise = firstValueFrom(service.login({ email: 'a@b.com', password: 'pw' }));
    const req = httpMock.expectOne(`${BASE_URL}/auth/login`);
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual({ email: 'a@b.com', password: 'pw' });
    req.flush(response);

    await expect(promise).resolves.toEqual(response);
  });
});
