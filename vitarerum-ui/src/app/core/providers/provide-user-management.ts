import { inject, Provider } from '@angular/core';
import { USE_MOCK_API } from '@core/config/app-config.model';
import {
  USER_MANAGEMENT_SERVICE,
  UserManagementService,
} from '@features/admin/services/user-management.service';
import { UserManagementServiceMock } from '@features/admin/services/user-management.service.mock';

export function provideUserManagement(): Provider[] {
  return [
    UserManagementService,
    UserManagementServiceMock,
    {
      provide: USER_MANAGEMENT_SERVICE,
      useFactory: () =>
        inject(USE_MOCK_API) ? inject(UserManagementServiceMock) : inject(UserManagementService),
    },
  ];
}
