import { HttpClient } from '@angular/common/http';
import { inject, Injectable, InjectionToken } from '@angular/core';
import { API_BASE_URL } from '@core/config/app-config.model';
import { buildApiUrl } from '@core/http/api-url.util';
import { buildHttpParams } from '@core/http/http-params.util';
import { Observable } from 'rxjs';

import {
  CreateReferencePolicyInput,
  PreviewReferencePolicyInput,
  ReferenceKind,
  ReferencePolicy,
  ReferencePolicyPreview,
} from '../models/reference-number-policy.model';

export interface ReferenceNumberPolicyApi {
  list(kind?: ReferenceKind): Observable<ReferencePolicy[]>;
  preview(input: PreviewReferencePolicyInput): Observable<ReferencePolicyPreview>;
  create(input: CreateReferencePolicyInput): Observable<ReferencePolicy>;
  activate(id: string): Observable<ReferencePolicy>;
  deactivate(id: string): Observable<ReferencePolicy>;
}

export const REFERENCE_NUMBER_POLICY_SERVICE = new InjectionToken<ReferenceNumberPolicyApi>(
  'REFERENCE_NUMBER_POLICY_SERVICE',
);

@Injectable()
export class ReferenceNumberPolicyService implements ReferenceNumberPolicyApi {
  private readonly http = inject(HttpClient);
  private readonly apiBaseUrl = inject(API_BASE_URL);

  list(kind?: ReferenceKind): Observable<ReferencePolicy[]> {
    return this.http.get<ReferencePolicy[]>(this.url('/admin/reference-number-policies'), {
      params: buildHttpParams({ kind }),
    });
  }

  preview(input: PreviewReferencePolicyInput): Observable<ReferencePolicyPreview> {
    return this.http.post<ReferencePolicyPreview>(
      this.url('/admin/reference-number-policies/preview'),
      input,
    );
  }

  create(input: CreateReferencePolicyInput): Observable<ReferencePolicy> {
    return this.http.post<ReferencePolicy>(this.url('/admin/reference-number-policies'), input);
  }

  activate(id: string): Observable<ReferencePolicy> {
    return this.http.post<ReferencePolicy>(
      this.url(`/admin/reference-number-policies/${id}/activate`),
      {},
    );
  }

  deactivate(id: string): Observable<ReferencePolicy> {
    return this.http.post<ReferencePolicy>(
      this.url(`/admin/reference-number-policies/${id}/deactivate`),
      {},
    );
  }

  private url(path: string): string {
    return buildApiUrl(this.apiBaseUrl, path);
  }
}
