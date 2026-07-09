import { HttpClient } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { API_BASE_URL } from '@core/config/app-config.model';
import { buildApiUrl } from '@core/http/api-url.util';
import { Observable } from 'rxjs';

import { LoginRequest, LoginResponse } from './models/login.model';
import {
  ChangePasswordRequest,
  PasswordResetConfirmRequest,
  PasswordResetRequest,
} from './models/password.model';

@Injectable({ providedIn: 'root' })
export class AuthApiService {
  private readonly http = inject(HttpClient);
  private readonly apiBaseUrl = inject(API_BASE_URL);

  login(request: LoginRequest): Observable<LoginResponse> {
    return this.http.post<LoginResponse>(buildApiUrl(this.apiBaseUrl, '/auth/login'), request);
  }

  changePassword(request: ChangePasswordRequest): Observable<void> {
    return this.http.post<void>(buildApiUrl(this.apiBaseUrl, '/auth/change-password'), request);
  }

  requestPasswordReset(request: PasswordResetRequest): Observable<void> {
    return this.http.post<void>(
      buildApiUrl(this.apiBaseUrl, '/auth/password-reset/request'),
      request,
    );
  }

  confirmPasswordReset(request: PasswordResetConfirmRequest): Observable<void> {
    return this.http.post<void>(
      buildApiUrl(this.apiBaseUrl, '/auth/password-reset/confirm'),
      request,
    );
  }
}
