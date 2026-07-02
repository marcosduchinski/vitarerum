import { inject, Provider } from '@angular/core';
import { USE_MOCK_API } from '@core/config/app-config.model';
import { DocumentTemplateManagementServiceMock } from '@features/admin/services/document-template-management.service.mock';
import {
  DOCUMENT_TEMPLATE_MANAGEMENT_SERVICE,
  DocumentTemplateManagementService,
} from '@features/admin/services/document-template-management.service';

export function provideDocumentTemplateManagement(): Provider[] {
  return [
    DocumentTemplateManagementService,
    DocumentTemplateManagementServiceMock,
    {
      provide: DOCUMENT_TEMPLATE_MANAGEMENT_SERVICE,
      useFactory: () =>
        inject(USE_MOCK_API)
          ? inject(DocumentTemplateManagementServiceMock)
          : inject(DocumentTemplateManagementService),
    },
  ];
}
