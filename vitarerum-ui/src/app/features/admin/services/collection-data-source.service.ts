import { HttpClient } from '@angular/common/http';
import { inject, Injectable, InjectionToken } from '@angular/core';
import { API_BASE_URL } from '@core/config/app-config.model';
import { buildApiUrl } from '@core/http/api-url.util';
import { map, Observable } from 'rxjs';

import {
  CollectionArea,
  CollectionCurator,
  CollectionDataSource,
  CuratorCandidate,
  SourceDocument,
  UpdateSourceDocumentObjectMappingRequest,
  UpdateCollectionRequest,
} from '../models/collection-data-source.model';

export interface CollectionDataSourceApi {
  listCollections(): Observable<CollectionDataSource[]>;
  createCollection(name: string, areaId: string): Observable<CollectionDataSource>;
  updateCollection(
    collectionId: string,
    changes: UpdateCollectionRequest,
  ): Observable<CollectionDataSource>;
  /** Permanently removes the collection and everything under it — curators,
   * source documents, indexed rows, and their files. Cannot be undone. */
  removeCollection(collectionId: string): Observable<void>;
  listDocuments(collectionId: string): Observable<SourceDocument[]>;
  listDocumentColumns(documentId: string): Observable<string[]>;
  previewDocumentColumns(collectionId: string, file: File): Observable<string[]>;
  updateObjectMapping(
    documentId: string,
    request: UpdateSourceDocumentObjectMappingRequest,
  ): Observable<SourceDocument>;
  upload(
    collectionId: string,
    file: File,
    objectMapping: UpdateSourceDocumentObjectMappingRequest,
  ): Observable<SourceDocument>;
  remove(documentId: string): Observable<void>;
  reindex(documentId: string): Observable<SourceDocument>;
  listCuratorCandidates(): Observable<CuratorCandidate[]>;
  assignCurator(collectionId: string, permissionId: string): Observable<CollectionCurator>;
  removeCurator(collectionId: string, permissionId: string): Observable<void>;
  listAreas(): Observable<CollectionArea[]>;
  createArea(name: string): Observable<CollectionArea>;
  updateArea(areaId: string, name: string): Observable<CollectionArea>;
  /** Rejects (409) while any collection is still assigned to the area. */
  removeArea(areaId: string): Observable<void>;
  moveCollectionToArea(collectionId: string, areaId: string): Observable<CollectionDataSource>;
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

  createCollection(name: string, areaId: string): Observable<CollectionDataSource> {
    return this.http.post<CollectionDataSource>(this.url('/collections'), { name, areaId });
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

  listDocumentColumns(documentId: string): Observable<string[]> {
    return this.http.get<{ columns: string[] }>(this.url(`/documents/${documentId}/columns`)).pipe(
      // Keep components decoupled from the tiny response wrapper.
      map((response) => response.columns),
    );
  }

  previewDocumentColumns(collectionId: string, file: File): Observable<string[]> {
    const form = new FormData();
    form.append('file', file, file.name);
    return this.http
      .post<{ columns: string[] }>(
        this.url(`/collections/${collectionId}/documents/columns-preview`),
        form,
      )
      .pipe(map((response) => response.columns));
  }

  updateObjectMapping(
    documentId: string,
    request: UpdateSourceDocumentObjectMappingRequest,
  ): Observable<SourceDocument> {
    return this.http.put<SourceDocument>(this.url(`/documents/${documentId}/object-mapping`), {
      inventoryNumberColumn: request.inventoryNumberColumn,
      displayTitleColumns: [...request.displayTitleColumns],
      objectNameColumn: request.objectNameColumn,
      descriptionColumns: [...request.descriptionColumns],
      searchableColumns: [...request.searchableColumns],
    });
  }

  upload(
    collectionId: string,
    file: File,
    objectMapping: UpdateSourceDocumentObjectMappingRequest,
  ): Observable<SourceDocument> {
    const form = new FormData();
    form.append('file', file, file.name);
    form.append('inventoryNumberColumn', objectMapping.inventoryNumberColumn);
    form.append('displayTitleColumns', JSON.stringify(objectMapping.displayTitleColumns));
    form.append('objectNameColumn', objectMapping.objectNameColumn ?? '');
    form.append('descriptionColumns', JSON.stringify(objectMapping.descriptionColumns));
    form.append('searchableColumns', JSON.stringify(objectMapping.searchableColumns));
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

  listAreas(): Observable<CollectionArea[]> {
    return this.http.get<CollectionArea[]>(this.url('/areas'));
  }

  createArea(name: string): Observable<CollectionArea> {
    return this.http.post<CollectionArea>(this.url('/areas'), { name });
  }

  updateArea(areaId: string, name: string): Observable<CollectionArea> {
    return this.http.patch<CollectionArea>(this.url(`/areas/${areaId}`), { name });
  }

  removeArea(areaId: string): Observable<void> {
    return this.http.delete<void>(this.url(`/areas/${areaId}`));
  }

  moveCollectionToArea(collectionId: string, areaId: string): Observable<CollectionDataSource> {
    return this.http.post<CollectionDataSource>(
      this.url(`/collections/${collectionId}/move-area`),
      { areaId },
    );
  }

  private url(path: string): string {
    return buildApiUrl(this.apiBaseUrl, `/admin/collection-data-sources${path}`);
  }
}
