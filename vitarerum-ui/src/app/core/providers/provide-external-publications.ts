import { inject, Provider } from '@angular/core';
import { USE_MOCK_API } from '@core/config/app-config.model';
import { ExternalPublicationServiceMock } from '@features/admin/services/external-publication.service.mock';
import {
  EXTERNAL_PUBLICATION_SERVICE,
  ExternalPublicationService,
} from '@features/admin/services/external-publication.service';

export function provideExternalPublications(): Provider[] {
  return [
    ExternalPublicationService,
    ExternalPublicationServiceMock,
    {
      provide: EXTERNAL_PUBLICATION_SERVICE,
      useFactory: () =>
        inject(USE_MOCK_API)
          ? inject(ExternalPublicationServiceMock)
          : inject(ExternalPublicationService),
    },
  ];
}
