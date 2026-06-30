import { inject, Provider } from '@angular/core';
import { USE_MOCK_API } from '@core/config/app-config.model';
import {
  INSTITUTION_MANAGEMENT_SERVICE,
  InstitutionManagementService,
} from '@features/admin/services/institution-management.service';
import { InstitutionManagementServiceMock } from '@features/admin/services/institution-management.service.mock';

export function provideInstitutionManagement(): Provider[] {
  return [
    InstitutionManagementService,
    InstitutionManagementServiceMock,
    {
      provide: INSTITUTION_MANAGEMENT_SERVICE,
      useFactory: () =>
        inject(USE_MOCK_API)
          ? inject(InstitutionManagementServiceMock)
          : inject(InstitutionManagementService),
    },
  ];
}
