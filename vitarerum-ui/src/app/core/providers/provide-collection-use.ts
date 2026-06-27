import { inject, Provider } from '@angular/core';
import { USE_MOCK_API } from '@core/config/app-config.model';
import { ProposalApiServiceMock } from '@features/collections/proposals/mocks/proposal-api.service.mock';
import { MOCK_SEED, MockProjectState, TEST_SEED } from '@features/collections/proposals/mocks/mock-data';
import { ProjectApiServiceMock } from '@features/collections/projects/mocks/project-api.service.mock';
import { ReportsApiServiceMock } from '@features/collections/reports/mocks/reports-api.service.mock';
import {
  PROJECT_API_SERVICE,
  ProjectApiService,
} from '@features/collections/projects/services/project-api.service';
import {
  PROPOSAL_API_SERVICE,
  ProposalApiService,
} from '@features/collections/proposals/services/proposal-api.service';
import {
  REPORTS_API_SERVICE,
  ReportsApiService,
} from '@features/collections/reports/services/reports-api.service';

export function provideCollectionUse(): Provider[] {
  return [
    // Seed the mock proposal/project stores so the running mock app shows a full
    // set of proposals (SUBMITTED, PENDING, APPROVED, REJECTED) and their
    // corresponding projects (CREATED, IN_PROGRESS, COMPLETED, CANCELLED).
    // Unused by the real API services, so it is safe to provide unconditionally.
    { provide: MOCK_SEED, useValue: TEST_SEED },
    MockProjectState,
    ProposalApiService,
    ProposalApiServiceMock,
    {
      provide: PROPOSAL_API_SERVICE,
      useFactory: () =>
        inject(USE_MOCK_API) ? inject(ProposalApiServiceMock) : inject(ProposalApiService),
    },
    ProjectApiService,
    ProjectApiServiceMock,
    {
      provide: PROJECT_API_SERVICE,
      useFactory: () =>
        inject(USE_MOCK_API) ? inject(ProjectApiServiceMock) : inject(ProjectApiService),
    },
    ReportsApiService,
    ReportsApiServiceMock,
    {
      provide: REPORTS_API_SERVICE,
      useFactory: () =>
        inject(USE_MOCK_API) ? inject(ReportsApiServiceMock) : inject(ReportsApiService),
    },
  ];
}
