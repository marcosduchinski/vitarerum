import { inject, Provider } from '@angular/core';
import { USE_MOCK_API } from '@core/config/app-config.model';
import { NotificationApiServiceMock } from '@features/notifications/mocks/notification-api.service.mock';
import {
  NOTIFICATION_API_SERVICE,
  NotificationApiService,
} from '@features/notifications/services/notification-api.service';

export function provideNotifications(): Provider[] {
  return [
    NotificationApiService,
    NotificationApiServiceMock,
    {
      provide: NOTIFICATION_API_SERVICE,
      useFactory: () =>
        inject(USE_MOCK_API) ? inject(NotificationApiServiceMock) : inject(NotificationApiService),
    },
  ];
}
