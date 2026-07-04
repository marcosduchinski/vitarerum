import { Injectable } from '@angular/core';
import { delay, Observable, of, throwError } from 'rxjs';

import {
  CollectionCurator,
  CollectionDataSource,
  SourceDocument,
} from '../models/collection-data-source.model';
import { CollectionDataSourceApi } from './collection-data-source.service';

const COLLECTION_NAMES = [
  'Biological Anthropology',
  'Archaeology',
  'Animal Sound Archive',
  'Historical Archives & Libraries',
  'Biological Banks',
  'Botany',
  'Ethnography',
  'Photography, Film & Audio',
  'History of Science and Medicine',
  'Institutional History & Art',
  'Mineralogy & Petrology',
  'Natural Objects',
  'Paleontology',
  'Zoology',
];

let _seq = 0;

@Injectable()
export class CollectionDataSourceServiceMock implements CollectionDataSourceApi {
  private documents = new Map<string, SourceDocument[]>([
    [
      'col-13',
      [
        {
          id: 'doc-1',
          collectionId: 'col-13',
          fileName: 'zoology-inventory.xlsx',
          sourceKind: 'UPLOAD',
          status: 'INDEXED',
          errorMessage: null,
          rowCount: 412,
          uploadedAt: '2026-06-20T10:00:00Z',
          indexedAt: '2026-06-20T10:00:03Z',
        },
      ],
    ],
  ]);

  private curators = new Map<string, CollectionCurator[]>([
    [
      'col-13',
      [
        {
          permissionId: 'perm-cur-1',
          name: 'Grace Curator',
          email: 'grace@museum.test',
          assignedAt: '2026-06-01T09:00:00Z',
        },
      ],
    ],
  ]);

  listCollections(): Observable<CollectionDataSource[]> {
    return of(
      COLLECTION_NAMES.map((name, i) => ({
        id: `col-${i}`,
        name,
        active: true,
        curators: this.curators.get(`col-${i}`) ?? [],
        documentCount: (this.documents.get(`col-${i}`) ?? []).length,
        manageable: true,
      })),
    ).pipe(delay(300));
  }

  listDocuments(collectionId: string): Observable<SourceDocument[]> {
    return of([...(this.documents.get(collectionId) ?? [])]).pipe(delay(200));
  }

  upload(collectionId: string, file: File): Observable<SourceDocument> {
    if (!file.name.toLowerCase().endsWith('.xlsx')) {
      return throwError(() => ({
        status: 415,
        error: { message: 'Only valid .xlsx files are accepted' },
      }));
    }
    const document: SourceDocument = {
      id: `doc-new-${++_seq}`,
      collectionId,
      fileName: file.name,
      sourceKind: 'UPLOAD',
      status: 'INDEXED',
      errorMessage: null,
      rowCount: 42,
      uploadedAt: new Date().toISOString(),
      indexedAt: new Date().toISOString(),
    };
    this.documents.set(collectionId, [document, ...(this.documents.get(collectionId) ?? [])]);
    return of(document).pipe(delay(400));
  }

  remove(documentId: string): Observable<void> {
    for (const [collectionId, docs] of this.documents) {
      this.documents.set(
        collectionId,
        docs.filter((d) => d.id !== documentId),
      );
    }
    return of(undefined).pipe(delay(200));
  }

  reindex(documentId: string): Observable<SourceDocument> {
    for (const docs of this.documents.values()) {
      const found = docs.find((d) => d.id === documentId);
      if (found) return of({ ...found, indexedAt: new Date().toISOString() }).pipe(delay(300));
    }
    return throwError(() => ({ status: 404, error: { message: 'Not found' } }));
  }

  assignCurator(collectionId: string, permissionId: string): Observable<CollectionCurator> {
    const curator: CollectionCurator = {
      permissionId,
      name: 'New Curator',
      email: 'curator@museum.test',
      assignedAt: new Date().toISOString(),
    };
    this.curators.set(collectionId, [...(this.curators.get(collectionId) ?? []), curator]);
    return of(curator).pipe(delay(200));
  }

  removeCurator(collectionId: string, permissionId: string): Observable<void> {
    this.curators.set(
      collectionId,
      (this.curators.get(collectionId) ?? []).filter((c) => c.permissionId !== permissionId),
    );
    return of(undefined).pipe(delay(200));
  }
}
