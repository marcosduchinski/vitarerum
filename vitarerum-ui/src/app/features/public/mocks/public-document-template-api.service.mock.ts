import { Injectable } from '@angular/core';
import { Observable, of } from 'rxjs';

import { UseType } from '@shared/models/collection-use-status.model';

import { PublicDocumentTemplate } from '../models/document-template.model';
import { PublicDocumentTemplateApi } from '../services/public-document-template-api.service';

const MOCK_TEMPLATES: Partial<Record<UseType, PublicDocumentTemplate[]>> = {
  IN_SITU_VISIT: [
    {
      id: 'tpl-safety',
      title: 'In-situ visit safety form',
      description: 'Download, complete and sign before your visit.',
      mandatory: true,
    },
    {
      id: 'tpl-equipment',
      title: 'Equipment declaration',
      description: 'List any equipment you intend to bring on site.',
      mandatory: false,
    },
  ],
  EXHIBITION: [
    {
      id: 'tpl-loan',
      title: 'Loan agreement template',
      description: 'Standard loan agreement for exhibition use.',
      mandatory: true,
    },
  ],
};

@Injectable()
export class PublicDocumentTemplateApiServiceMock implements PublicDocumentTemplateApi {
  listTemplates(useType: UseType): Observable<PublicDocumentTemplate[]> {
    return of(MOCK_TEMPLATES[useType] ?? []);
  }

  downloadUrl(id: string): string {
    return `#mock-template-${id}`;
  }
}
