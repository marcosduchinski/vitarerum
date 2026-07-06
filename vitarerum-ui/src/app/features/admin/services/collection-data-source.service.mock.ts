import { Injectable } from '@angular/core';
import { delay, Observable, of, throwError } from 'rxjs';

import {
  CollectionArea,
  CollectionCurator,
  CollectionDataSource,
  CuratorCandidate,
  SourceDocument,
  UpdateCollectionRequest,
} from '../models/collection-data-source.model';
import { CollectionDataSourceApi } from './collection-data-source.service';

const AREA_NAMES = ['Natural History', 'Human Sciences', 'Documentation & Media'] as const;

// Mirrors the initial backfill in the backend's 0014_collection_areas migration.
const COLLECTION_SEEDS: readonly { name: string; area: (typeof AREA_NAMES)[number] }[] = [
  { name: 'Biological Banks', area: 'Natural History' },
  { name: 'Botany', area: 'Natural History' },
  { name: 'Mineralogy & Petrology', area: 'Natural History' },
  { name: 'Natural Objects', area: 'Natural History' },
  { name: 'Paleontology', area: 'Natural History' },
  { name: 'Zoology', area: 'Natural History' },
  { name: 'Biological Anthropology', area: 'Human Sciences' },
  { name: 'Archaeology', area: 'Human Sciences' },
  { name: 'Ethnography', area: 'Human Sciences' },
  { name: 'History of Science and Medicine', area: 'Human Sciences' },
  { name: 'Institutional History & Art', area: 'Human Sciences' },
  { name: 'Animal Sound Archive', area: 'Documentation & Media' },
  { name: 'Historical Archives & Libraries', area: 'Documentation & Media' },
  { name: 'Photography, Film & Audio', area: 'Documentation & Media' },
];

let _seq = 0;

@Injectable()
export class CollectionDataSourceServiceMock implements CollectionDataSourceApi {
  private documents = new Map<string, SourceDocument[]>([
    [
      'col-5',
      [
        {
          id: 'doc-1',
          collectionId: 'col-5',
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

  private areas: CollectionArea[] = AREA_NAMES.map((name, i) => ({
    id: `area-${i}`,
    name,
    collectionCount: COLLECTION_SEEDS.filter((seed) => seed.area === name).length,
  }));

  private collections: CollectionDataSource[] = COLLECTION_SEEDS.map((seed, i) => {
    const areaIndex = AREA_NAMES.indexOf(seed.area);
    return {
      id: `col-${i}`,
      areaId: `area-${areaIndex}`,
      areaName: seed.area,
      name: seed.name,
      curators:
        `col-${i}` === 'col-5'
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
    };
  });

  listCollections(): Observable<CollectionDataSource[]> {
    return of([...this.collections]).pipe(delay(300));
  }

  createCollection(name: string, areaId: string): Observable<CollectionDataSource> {
    const area = this.areas.find((a) => a.id === areaId);
    if (!area) {
      return throwError(() => ({
        status: 404,
        error: { error: 'COLLECTION_AREA_NOT_FOUND', message: 'No collection area found' },
      }));
    }
    const collection: CollectionDataSource = {
      id: `col-new-${++_seq}`,
      areaId: area.id,
      areaName: area.name,
      name,
      curators: [],
      documentCount: 0,
      manageable: true,
    };
    this.collections = [collection, ...this.collections];
    this.recomputeAreaCounts();
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
    this.recomputeAreaCounts();
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
      c.id === collectionId &&
      !c.curators.some((existing) => existing.permissionId === permissionId)
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

  listAreas(): Observable<CollectionArea[]> {
    return of([...this.areas]).pipe(delay(200));
  }

  createArea(name: string): Observable<CollectionArea> {
    if (this.areas.some((a) => a.name === name)) {
      return throwError(() => ({
        status: 409,
        error: {
          error: 'COLLECTION_AREA_NAME_ALREADY_EXISTS',
          message: 'A collection area with this name already exists',
        },
      }));
    }
    const area: CollectionArea = { id: `area-new-${++_seq}`, name, collectionCount: 0 };
    this.areas = [...this.areas, area];
    return of(area).pipe(delay(300));
  }

  updateArea(areaId: string, name: string): Observable<CollectionArea> {
    const index = this.areas.findIndex((a) => a.id === areaId);
    if (index === -1) {
      return throwError(() => ({
        status: 404,
        error: { error: 'COLLECTION_AREA_NOT_FOUND', message: 'No collection area found' },
      }));
    }
    const updated: CollectionArea = { ...this.areas[index], name };
    this.areas = this.areas.map((a, i) => (i === index ? updated : a));
    this.collections = this.collections.map((c) =>
      c.areaId === areaId ? { ...c, areaName: name } : c,
    );
    return of(updated).pipe(delay(200));
  }

  removeArea(areaId: string): Observable<void> {
    const area = this.areas.find((a) => a.id === areaId);
    if (!area) {
      return throwError(() => ({
        status: 404,
        error: { error: 'COLLECTION_AREA_NOT_FOUND', message: 'No collection area found' },
      }));
    }
    if (this.collections.some((c) => c.areaId === areaId)) {
      return throwError(() => ({
        status: 409,
        error: {
          error: 'COLLECTION_AREA_IN_USE',
          message: 'Collection area still has collections assigned to it',
        },
      }));
    }
    this.areas = this.areas.filter((a) => a.id !== areaId);
    return of(undefined).pipe(delay(200));
  }

  moveCollectionToArea(collectionId: string, areaId: string): Observable<CollectionDataSource> {
    const area = this.areas.find((a) => a.id === areaId);
    if (!area) {
      return throwError(() => ({
        status: 404,
        error: { error: 'COLLECTION_AREA_NOT_FOUND', message: 'No collection area found' },
      }));
    }
    const index = this.collections.findIndex((c) => c.id === collectionId);
    if (index === -1) {
      return throwError(() => ({
        status: 404,
        error: { error: 'COLLECTION_NOT_FOUND', message: 'No collection found' },
      }));
    }
    const updated: CollectionDataSource = {
      ...this.collections[index],
      areaId: area.id,
      areaName: area.name,
    };
    this.collections = this.collections.map((c, i) => (i === index ? updated : c));
    this.recomputeAreaCounts();
    return of(updated).pipe(delay(200));
  }

  private recomputeAreaCounts(): void {
    this.areas = this.areas.map((area) => ({
      ...area,
      collectionCount: this.collections.filter((c) => c.areaId === area.id).length,
    }));
  }
}
