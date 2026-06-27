import { inject, Provider } from '@angular/core';
import { USE_MOCK_API } from '@core/config/app-config.model';
import { PublicProposalApiServiceMock } from '@features/public/mocks/public-proposal-api.service.mock';
import {
  PUBLIC_PROPOSAL_API_SERVICE,
  PublicProposalApiService,
} from '@features/public/services/public-proposal-api.service';

/**
 * Providers for the public proposal submission feature. Registered at the
 * public route level so they are not loaded by the authenticated app, and so
 * the real/mock choice follows USE_MOCK_API like the other features
 * (cf. provide-collection-use.ts).
 */
export function providePublicSubmission(): Provider[] {
  return [
    PublicProposalApiService,
    PublicProposalApiServiceMock,
    {
      provide: PUBLIC_PROPOSAL_API_SERVICE,
      useFactory: () =>
        inject(USE_MOCK_API)
          ? inject(PublicProposalApiServiceMock)
          : inject(PublicProposalApiService),
    },
  ];
}
