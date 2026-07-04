import { HttpClient } from '@angular/common/http';
import { inject, Injectable, InjectionToken } from '@angular/core';
import { API_BASE_URL } from '@core/config/app-config.model';
import { buildApiUrl } from '@core/http/api-url.util';
import { buildHttpParams } from '@core/http/http-params.util';
import { Observable } from 'rxjs';

import {
  ObjectSearchQuery,
  ObjectSearchResult,
  SearchableCollection,
} from '../models/object-search.model';

export interface ObjectSearchApi {
  search(query: ObjectSearchQuery): Observable<ObjectSearchResult>;
  listSearchableCollections(): Observable<SearchableCollection[]>;
}

export const OBJECT_SEARCH_SERVICE = new InjectionToken<ObjectSearchApi>('OBJECT_SEARCH_SERVICE');

@Injectable()
export class ObjectSearchService implements ObjectSearchApi {
  private readonly http = inject(HttpClient);
  private readonly apiBaseUrl = inject(API_BASE_URL);

  search(query: ObjectSearchQuery): Observable<ObjectSearchResult> {
    return this.http.get<ObjectSearchResult>(this.url('/search'), {
      params: buildHttpParams({
        q: query.q,
        collectionId: query.collectionId,
        page: query.page,
        size: query.size,
      }),
    });
  }

  listSearchableCollections(): Observable<SearchableCollection[]> {
    return this.http.get<SearchableCollection[]>(this.url('/search/collections'));
  }

  private url(path: string): string {
    return buildApiUrl(this.apiBaseUrl, `/objects${path}`);
  }
}
