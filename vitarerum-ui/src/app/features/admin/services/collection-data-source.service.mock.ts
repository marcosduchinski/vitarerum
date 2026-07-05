import { Injectable } from '@angular/core';
import { delay, Observable, of, throwError } from 'rxjs';

import {
  CollectionCurator,
  CollectionDataSource,
  CuratorCandidate,
  SourceDocument,
  UpdateCollectionRequest,
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

  private readonly curatorCandidates: CuratorCandidate[] = [
    { permissionId: 'perm-cur-1', name: 'Grace Curator', email: 'grace@museum.test' },
    { permissionId: 'perm-cur-2', name: 'Hugo Curator', email: 'hugo@museum.test' },
  ];

  private collections: CollectionDataSource[] = COLLECTION_NAMES.map((name, i) => ({
    id: `col-${i}`,
    name,
    curators:
      `col-${i}` === 'col-13'
        ? [
            {
              permissionId: 'perm-cur-1',
              name: 'Grace Curator',
              email: 'grace@museum.test',
              assignedAt: '2026-06-01T09:00:00Z',
            },
          ]
        : [],
    documentCount: (this.documents.get(`col-${i}`) ?? []).length,
    manageable: true,
  }));

  listCollections(): Observable<CollectionDataSource[]> {
    return of([...this.collections]).pipe(delay(300));
  }

  createCollection(name: string): Observable<CollectionDataSource> {
    const collection: CollectionDataSource = {
      id: `col-new-${++_seq}`,
      name,
      curators: [],
      documentCount: 0,
      manageable: true,
    };
    this.collections = [collection, ...this.collections];
    return of(collection).pipe(delay(300));
  }

  updateCollection(
    collectionId: string,
    changes: UpdateCollectionRequest,
  ): Observable<CollectionDataSource> {
    const index = this.collections.findIndex((c) => c.id === collectionId);
    if (index === -1) {
      return throwError(() => ({ status: 404, error: { message: 'Not found' } }));
    }
    const updated: CollectionDataSource = { ...this.collections[index], name: changes.name };
    this.collections = this.collections.map((c, i) => (i === index ? updated : c));
    return of(updated).pipe(delay(200));
  }

  removeCollection(collectionId: string): Observable<void> {
    this.collections = this.collections.filter((c) => c.id !== collectionId);
    this.documents.delete(collectionId);
    return of(undefined).pipe(delay(300));
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
    this.bumpDocumentCount(collectionId, 1);
    return of(document).pipe(delay(400));
  }

  remove(documentId: string): Observable<void> {
    for (const [collectionId, docs] of this.documents) {
      if (docs.some((d) => d.id === documentId)) {
        this.documents.set(
          collectionId,
          docs.filter((d) => d.id !== documentId),
        );
        this.bumpDocumentCount(collectionId, -1);
      }
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

  listCuratorCandidates(): Observable<CuratorCandidate[]> {
    return of([...this.curatorCandidates]).pipe(delay(150));
  }

  assignCurator(collectionId: string, permissionId: string): Observable<CollectionCurator> {
    const candidate = this.curatorCandidates.find((c) => c.permissionId === permissionId);
    const curator: CollectionCurator = {
      permissionId,
      name: candidate?.name ?? 'New Curator',
      email: candidate?.email ?? 'curator@museum.test',
      assignedAt: new Date().toISOString(),
    };
    this.collections = this.collections.map((c) =>
      c.id === collectionId && !c.curators.some((existing) => existing.permissionId === permissionId)
        ? { ...c, curators: [...c.curators, curator] }
        : c,
    );
    return of(curator).pipe(delay(200));
  }

  removeCurator(collectionId: string, permissionId: string): Observable<void> {
    this.collections = this.collections.map((c) =>
      c.id === collectionId
        ? { ...c, curators: c.curators.filter((curator) => curator.permissionId !== permissionId) }
        : c,
    );
    return of(undefined).pipe(delay(200));
  }

  private bumpDocumentCount(collectionId: string, delta: number): void {
    this.collections = this.collections.map((c) =>
      c.id === collectionId ? { ...c, documentCount: c.documentCount + delta } : c,
    );
  }
}
