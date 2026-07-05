import { inject, Provider } from '@angular/core';
import { USE_MOCK_API } from '@core/config/app-config.model';
import { MuseumQuestionManagementServiceMock } from '@features/museum-questions/mocks/museum-question-management.service.mock';
import {
  MUSEUM_QUESTION_MANAGEMENT_SERVICE,
  MuseumQuestionManagementService,
} from '@features/museum-questions/services/museum-question-management.service';

export function provideMuseumQuestionManagement(): Provider[] {
  return [
    MuseumQuestionManagementService,
    MuseumQuestionManagementServiceMock,
    {
      provide: MUSEUM_QUESTION_MANAGEMENT_SERVICE,
      useFactory: () =>
        inject(USE_MOCK_API)
          ? inject(MuseumQuestionManagementServiceMock)
          : inject(MuseumQuestionManagementService),
    },
  ];
}
