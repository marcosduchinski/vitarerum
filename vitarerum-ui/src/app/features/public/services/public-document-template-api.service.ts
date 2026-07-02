import { HttpClient } from '@angular/common/http';
import { inject, Injectable, InjectionToken } from '@angular/core';
import { API_BASE_URL } from '@core/config/app-config.model';
import { buildApiUrl } from '@core/http/api-url.util';
import { Observable } from 'rxjs';

import { UseType } from '@shared/models/collection-use-status.model';

import { PublicDocumentTemplate } from '../models/document-template.model';

export interface PublicDocumentTemplateApi {
  /** Active templates offered for the given use type, in display order. */
  listTemplates(useType: UseType): Observable<PublicDocumentTemplate[]>;
  /** Direct (unauthenticated) download URL for a template's .docx file. */
  downloadUrl(id: string): string;
}

export const PUBLIC_DOCUMENT_TEMPLATE_API_SERVICE =
  new InjectionToken<PublicDocumentTemplateApi>('PUBLIC_DOCUMENT_TEMPLATE_API_SERVICE');

/**
 * Talks to the PUBLIC document-template endpoints. Unauthenticated, like the
 * rest of the public submission flow; the download is a plain link so the
 * browser fetches the file directly.
 */
@Injectable()
export class PublicDocumentTemplateApiService implements PublicDocumentTemplateApi {
  private readonly http = inject(HttpClient);
  private readonly apiBaseUrl = inject(API_BASE_URL);

  listTemplates(useType: UseType): Observable<PublicDocumentTemplate[]> {
    return this.http.get<PublicDocumentTemplate[]>(this.url('/public/document-templates'), {
      params: { useType },
    });
  }

  downloadUrl(id: string): string {
    return this.url(`/public/document-templates/${id}/file`);
  }

  private url(path: string): string {
    return buildApiUrl(this.apiBaseUrl, path);
  }
}
