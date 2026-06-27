import { HttpClient } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { API_BASE_URL } from '@core/config/app-config.model';
import { buildApiUrl } from '@core/http/api-url.util';
import { Observable } from 'rxjs';

import { LoginRequest, LoginResponse } from './models/login.model';

@Injectable({ providedIn: 'root' })
export class AuthApiService {
  private readonly http = inject(HttpClient);
  private readonly apiBaseUrl = inject(API_BASE_URL);

  login(request: LoginRequest): Observable<LoginResponse> {
    return this.http.post<LoginResponse>(buildApiUrl(this.apiBaseUrl, '/auth/login'), request);
  }
}
