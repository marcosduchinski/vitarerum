import { HttpClient } from '@angular/common/http';
import { inject, Injectable, InjectionToken } from '@angular/core';
import { API_BASE_URL } from '@core/config/app-config.model';
import { buildApiUrl } from '@core/http/api-url.util';
import { Observable } from 'rxjs';

import {
  CollectionCurator,
  CollectionDataSource,
  CuratorCandidate,
  SourceDocument,
  UpdateCollectionRequest,
} from '../models/collection-data-source.model';

export interface CollectionDataSourceApi {
  listCollections(): Observable<CollectionDataSource[]>;
  createCollection(name: string): Observable<CollectionDataSource>;
  updateCollection(
    collectionId: string,
    changes: UpdateCollectionRequest,
  ): Observable<CollectionDataSource>;
  /** Permanently removes the collection and everything under it — curators,
   * source documents, indexed rows, and their files. Cannot be undone. */
  removeCollection(collectionId: string): Observable<void>;
  listDocuments(collectionId: string): Observable<SourceDocument[]>;
  upload(collectionId: string, file: File): Observable<SourceDocument>;
  remove(documentId: string): Observable<void>;
  reindex(documentId: string): Observable<SourceDocument>;
  listCuratorCandidates(): Observable<CuratorCandidate[]>;
  assignCurator(collectionId: string, permissionId: string): Observable<CollectionCurator>;
  removeCurator(collectionId: string, permissionId: string): Observable<void>;
}

export const COLLECTION_DATA_SOURCE_SERVICE = new InjectionToken<CollectionDataSourceApi>(
  'COLLECTION_DATA_SOURCE_SERVICE',
);

@Injectable()
export class CollectionDataSourceService implements CollectionDataSourceApi {
  private readonly http = inject(HttpClient);
  private readonly apiBaseUrl = inject(API_BASE_URL);

  listCollections(): Observable<CollectionDataSource[]> {
    return this.http.get<CollectionDataSource[]>(this.url('/collections'));
  }

  createCollection(name: string): Observable<CollectionDataSource> {
    return this.http.post<CollectionDataSource>(this.url('/collections'), { name });
  }

  updateCollection(
    collectionId: string,
    changes: UpdateCollectionRequest,
  ): Observable<CollectionDataSource> {
    return this.http.patch<CollectionDataSource>(this.url(`/collections/${collectionId}`), changes);
  }

  removeCollection(collectionId: string): Observable<void> {
    return this.http.delete<void>(this.url(`/collections/${collectionId}`));
  }

  listDocuments(collectionId: string): Observable<SourceDocument[]> {
    return this.http.get<SourceDocument[]>(this.url(`/collections/${collectionId}/documents`));
  }

  upload(collectionId: string, file: File): Observable<SourceDocument> {
    const form = new FormData();
    form.append('file', file, file.name);
    return this.http.post<SourceDocument>(this.url(`/collections/${collectionId}/documents`), form);
  }

  remove(documentId: string): Observable<void> {
    return this.http.delete<void>(this.url(`/documents/${documentId}`));
  }

  reindex(documentId: string): Observable<SourceDocument> {
    return this.http.post<SourceDocument>(this.url(`/documents/${documentId}/reindex`), {});
  }

  listCuratorCandidates(): Observable<CuratorCandidate[]> {
    return this.http.get<CuratorCandidate[]>(this.url('/curator-candidates'));
  }

  assignCurator(collectionId: string, permissionId: string): Observable<CollectionCurator> {
    return this.http.post<CollectionCurator>(this.url(`/collections/${collectionId}/curators`), {
      permissionId,
    });
  }

  removeCurator(collectionId: string, permissionId: string): Observable<void> {
    return this.http.delete<void>(
      this.url(`/collections/${collectionId}/curators/${permissionId}`),
    );
  }

  private url(path: string): string {
    return buildApiUrl(this.apiBaseUrl, `/admin/collection-data-sources${path}`);
  }
}
