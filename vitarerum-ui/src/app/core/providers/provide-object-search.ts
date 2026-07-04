import { inject, Provider } from '@angular/core';
import { USE_MOCK_API } from '@core/config/app-config.model';
import { ObjectSearchServiceMock } from '@features/objects/services/object-search.service.mock';
import {
  OBJECT_SEARCH_SERVICE,
  ObjectSearchService,
} from '@features/objects/services/object-search.service';

export function provideObjectSearch(): Provider[] {
  return [
    ObjectSearchService,
    ObjectSearchServiceMock,
    {
      provide: OBJECT_SEARCH_SERVICE,
      useFactory: () =>
        inject(USE_MOCK_API) ? inject(ObjectSearchServiceMock) : inject(ObjectSearchService),
    },
  ];
}
