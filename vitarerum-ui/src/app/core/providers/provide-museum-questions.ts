import { inject, Provider } from '@angular/core';
import { USE_MOCK_API } from '@core/config/app-config.model';
import { MuseumQuestionApiServiceMock } from '@features/public/mocks/museum-question-api.service.mock';
import {
  MUSEUM_QUESTION_API_SERVICE,
  MuseumQuestionApiService,
} from '@features/public/services/museum-question-api.service';

/**
 * Providers for the public "Pergunte ao Museu" feature. Registered at the
 * public route level so they are not loaded by the authenticated app, and so
 * the real/mock choice follows USE_MOCK_API like the other public features
 * (cf. provide-public-submission.ts).
 */
export function provideMuseumQuestions(): Provider[] {
  return [
    MuseumQuestionApiService,
    MuseumQuestionApiServiceMock,
    {
      provide: MUSEUM_QUESTION_API_SERVICE,
      useFactory: () =>
        inject(USE_MOCK_API)
          ? inject(MuseumQuestionApiServiceMock)
          : inject(MuseumQuestionApiService),
    },
  ];
}
