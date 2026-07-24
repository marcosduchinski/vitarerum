import { inject, Provider } from '@angular/core';
import { USE_MOCK_API } from '@core/config/app-config.model';
import { ReferenceNumberPolicyServiceMock } from '@features/admin/services/reference-number-policy.service.mock';
import {
  REFERENCE_NUMBER_POLICY_SERVICE,
  ReferenceNumberPolicyService,
} from '@features/admin/services/reference-number-policy.service';

export function provideReferenceNumberPolicies(): Provider[] {
  return [
    ReferenceNumberPolicyService,
    ReferenceNumberPolicyServiceMock,
    {
      provide: REFERENCE_NUMBER_POLICY_SERVICE,
      useFactory: () =>
        inject(USE_MOCK_API)
          ? inject(ReferenceNumberPolicyServiceMock)
          : inject(ReferenceNumberPolicyService),
    },
  ];
}
