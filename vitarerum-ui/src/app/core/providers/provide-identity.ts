import { inject, Provider } from '@angular/core';
import { USE_MOCK_AUTH } from '@core/config/app-config.model';
import { IDENTITY_SERVICE } from '@core/auth/identity.service';
import { IdentityServiceImpl } from '@core/auth/identity.service.impl';
import { IdentityServiceMock } from '@core/auth/identity.service.mock';

export function provideIdentity(): Provider[] {
  return [
    IdentityServiceImpl,
    IdentityServiceMock,
    {
      provide: IDENTITY_SERVICE,
      useFactory: () =>
        inject(USE_MOCK_AUTH) ? inject(IdentityServiceMock) : inject(IdentityServiceImpl),
    },
  ];
}
