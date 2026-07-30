import { HttpClient } from '@angular/common/http';
import { inject, Injectable, InjectionToken } from '@angular/core';
import { API_BASE_URL } from '@core/config/app-config.model';
import { buildApiUrl } from '@core/http/api-url.util';
import { buildHttpParams } from '@core/http/http-params.util';
import { Page } from '@shared/models/page.model';
import { Observable } from 'rxjs';

import {
  CreateExternalPublicationRequest,
  ExternalPublication,
  ExternalPublicationFilters,
  PublishableResource,
  PublishableResourceFilters,
} from '../models/external-publication.model';

export interface ExternalPublicationApi {
  listPublications(filters: ExternalPublicationFilters): Observable<Page<ExternalPublication>>;
  listPublishableResources(filters: PublishableResourceFilters): Observable<Page<PublishableResource>>;
  createPublication(request: CreateExternalPublicationRequest): Observable<ExternalPublication>;
  revokePublication(publicationId: string): Observable<ExternalPublication>;
}

export const EXTERNAL_PUBLICATION_SERVICE = new InjectionToken<ExternalPublicationApi>(
  'EXTERNAL_PUBLICATION_SERVICE',
);

@Injectable()
export class ExternalPublicationService implements ExternalPublicationApi {
  private readonly http = inject(HttpClient);
  private readonly apiBaseUrl = inject(API_BASE_URL);

  listPublications(filters: ExternalPublicationFilters): Observable<Page<ExternalPublication>> {
    return this.http.get<Page<ExternalPublication>>(this.url('/external-publications'), {
      params: buildHttpParams(filters),
    });
  }

  listPublishableResources(filters: PublishableResourceFilters): Observable<Page<PublishableResource>> {
    return this.http.get<Page<PublishableResource>>(
      this.url('/external-publications/publishable-resources'),
      { params: buildHttpParams(filters) },
    );
  }

  createPublication(request: CreateExternalPublicationRequest): Observable<ExternalPublication> {
    return this.http.post<ExternalPublication>(this.url('/external-publications'), request);
  }

  revokePublication(publicationId: string): Observable<ExternalPublication> {
    return this.http.patch<ExternalPublication>(
      this.url(`/external-publications/${publicationId}/revoke`),
      {},
    );
  }

  private url(path: string): string {
    return buildApiUrl(this.apiBaseUrl, path);
  }
}
