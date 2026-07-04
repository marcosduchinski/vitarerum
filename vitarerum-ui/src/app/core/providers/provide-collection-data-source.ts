import { inject, Provider } from '@angular/core';
import { USE_MOCK_API } from '@core/config/app-config.model';
import { CollectionDataSourceServiceMock } from '@features/admin/services/collection-data-source.service.mock';
import {
  COLLECTION_DATA_SOURCE_SERVICE,
  CollectionDataSourceService,
} from '@features/admin/services/collection-data-source.service';

export function provideCollectionDataSource(): Provider[] {
  return [
    CollectionDataSourceService,
    CollectionDataSourceServiceMock,
    {
      provide: COLLECTION_DATA_SOURCE_SERVICE,
      useFactory: () =>
        inject(USE_MOCK_API)
          ? inject(CollectionDataSourceServiceMock)
          : inject(CollectionDataSourceService),
    },
  ];
}
