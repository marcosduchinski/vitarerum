import { HttpClient } from '@angular/common/http';
import { inject, Injectable, InjectionToken } from '@angular/core';
import { API_BASE_URL } from '@core/config/app-config.model';
import { buildApiUrl } from '@core/http/api-url.util';
import { buildHttpParams } from '@core/http/http-params.util';
import {
  Institution,
  InstitutionPayload,
} from '@core/auth/models/institution.model';
import { Page, PageQuery } from '@shared/models/page.model';
import { Observable } from 'rxjs';

export const INSTITUTION_MANAGEMENT_SERVICE =
  new InjectionToken<InstitutionManagementService>('INSTITUTION_MANAGEMENT_SERVICE');

@Injectable()
export class InstitutionManagementService {
  private readonly http = inject(HttpClient);
  private readonly apiBaseUrl = inject(API_BASE_URL);

  listInstitutions(query: PageQuery = {}): Observable<Page<Institution>> {
    return this.http.get<Page<Institution>>(this.url('/institutions'), {
      params: buildHttpParams(query),
    });
  }

  getInstitution(institutionId: string): Observable<Institution> {
    return this.http.get<Institution>(this.url(`/institutions/${institutionId}`));
  }

  createInstitution(payload: InstitutionPayload): Observable<Institution> {
    return this.http.post<Institution>(this.url('/institutions'), payload);
  }

  updateInstitution(
    institutionId: string,
    payload: InstitutionPayload,
  ): Observable<Institution> {
    return this.http.put<Institution>(
      this.url(`/institutions/${institutionId}`),
      payload,
    );
  }

  deleteInstitution(institutionId: string): Observable<void> {
    return this.http.delete<void>(this.url(`/institutions/${institutionId}`));
  }

  private url(path: string): string {
    return buildApiUrl(this.apiBaseUrl, path);
  }
}
