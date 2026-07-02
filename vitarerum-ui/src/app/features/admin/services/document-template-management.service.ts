import { HttpClient } from '@angular/common/http';
import { inject, Injectable, InjectionToken } from '@angular/core';
import { API_BASE_URL } from '@core/config/app-config.model';
import { buildApiUrl } from '@core/http/api-url.util';
import { buildHttpParams } from '@core/http/http-params.util';
import { Observable } from 'rxjs';

import { UseType } from '@shared/models/collection-use-status.model';

import {
  CreateDocumentTemplateInput,
  DocumentTemplate,
  DocumentTemplateMetadata,
} from '../models/document-template.model';

export interface DocumentTemplateManagementApi {
  list(useType?: UseType): Observable<DocumentTemplate[]>;
  create(input: CreateDocumentTemplateInput): Observable<DocumentTemplate>;
  updateMetadata(id: string, metadata: DocumentTemplateMetadata): Observable<DocumentTemplate>;
  replaceFile(id: string, file: File): Observable<DocumentTemplate>;
  remove(id: string): Observable<void>;
  downloadFile(id: string): Observable<Blob>;
}

export const DOCUMENT_TEMPLATE_MANAGEMENT_SERVICE =
  new InjectionToken<DocumentTemplateManagementApi>('DOCUMENT_TEMPLATE_MANAGEMENT_SERVICE');

@Injectable()
export class DocumentTemplateManagementService implements DocumentTemplateManagementApi {
  private readonly http = inject(HttpClient);
  private readonly apiBaseUrl = inject(API_BASE_URL);

  list(useType?: UseType): Observable<DocumentTemplate[]> {
    return this.http.get<DocumentTemplate[]>(this.url('/document-templates'), {
      params: buildHttpParams({ useType }),
    });
  }

  create(input: CreateDocumentTemplateInput): Observable<DocumentTemplate> {
    const form = new FormData();
    form.append('file', input.file, input.file.name);
    form.append('useType', input.useType);
    form.append('title', input.title);
    form.append('description', input.description);
    form.append('mandatory', String(input.mandatory));
    form.append('active', String(input.active));
    form.append('displayOrder', String(input.displayOrder));
    return this.http.post<DocumentTemplate>(this.url('/document-templates'), form);
  }

  updateMetadata(id: string, metadata: DocumentTemplateMetadata): Observable<DocumentTemplate> {
    return this.http.patch<DocumentTemplate>(this.url(`/document-templates/${id}`), metadata);
  }

  replaceFile(id: string, file: File): Observable<DocumentTemplate> {
    const form = new FormData();
    form.append('file', file, file.name);
    return this.http.put<DocumentTemplate>(this.url(`/document-templates/${id}/file`), form);
  }

  remove(id: string): Observable<void> {
    return this.http.delete<void>(this.url(`/document-templates/${id}`));
  }

  downloadFile(id: string): Observable<Blob> {
    return this.http.get(this.url(`/document-templates/${id}/file`), {
      responseType: 'blob',
    });
  }

  private url(path: string): string {
    return buildApiUrl(this.apiBaseUrl, path);
  }
}
