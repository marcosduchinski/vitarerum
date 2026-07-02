import { Injectable } from '@angular/core';
import { Observable, of } from 'rxjs';

import { UseType } from '@shared/models/collection-use-status.model';

import {
  CreateDocumentTemplateInput,
  DocumentTemplate,
  DocumentTemplateMetadata,
} from '../models/document-template.model';
import { DocumentTemplateManagementApi } from './document-template-management.service';

let _seq = 0;

@Injectable()
export class DocumentTemplateManagementServiceMock implements DocumentTemplateManagementApi {
  private templates: DocumentTemplate[] = [
    {
      id: 'tpl-safety',
      useType: 'IN_SITU_VISIT',
      title: 'In-situ visit safety form',
      description: 'Download, complete and sign before your visit.',
      mandatory: true,
      active: true,
      displayOrder: 0,
      fileName: 'safety-form.docx',
      uploadedAt: '2026-06-01T09:00:00Z',
    },
  ];

  list(useType?: UseType): Observable<DocumentTemplate[]> {
    const items = useType ? this.templates.filter((t) => t.useType === useType) : this.templates;
    return of([...items]);
  }

  create(input: CreateDocumentTemplateInput): Observable<DocumentTemplate> {
    const created: DocumentTemplate = {
      id: `tpl-mock-${(_seq += 1)}`,
      useType: input.useType,
      title: input.title,
      description: input.description,
      mandatory: input.mandatory,
      active: input.active,
      displayOrder: input.displayOrder,
      fileName: input.file.name,
      uploadedAt: new Date().toISOString(),
    };
    this.templates = [...this.templates, created];
    return of(created);
  }

  updateMetadata(id: string, metadata: DocumentTemplateMetadata): Observable<DocumentTemplate> {
    let updated!: DocumentTemplate;
    this.templates = this.templates.map((t) => {
      if (t.id !== id) return t;
      updated = { ...t, ...metadata };
      return updated;
    });
    return of(updated);
  }

  replaceFile(id: string, file: File): Observable<DocumentTemplate> {
    let updated!: DocumentTemplate;
    this.templates = this.templates.map((t) => {
      if (t.id !== id) return t;
      updated = { ...t, fileName: file.name };
      return updated;
    });
    return of(updated);
  }

  remove(id: string): Observable<void> {
    this.templates = this.templates.filter((t) => t.id !== id);
    return of(undefined);
  }

  downloadFile(): Observable<Blob> {
    return of(new Blob(['mock template'], { type: 'text/plain' }));
  }
}
