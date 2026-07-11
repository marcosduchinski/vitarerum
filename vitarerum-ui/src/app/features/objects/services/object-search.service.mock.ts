import { Injectable } from '@angular/core';
import { delay, Observable, of } from 'rxjs';

import {
  ObjectSearchHit,
  ObjectSearchQuery,
  ObjectSearchResult,
  SearchableCollection,
} from '../models/object-search.model';
import { ObjectSearchApi } from './object-search.service';

interface MockRow extends ObjectSearchHit {
  readonly content: string;
}

const COLLECTIONS: SearchableCollection[] = [
  { id: 'col-zoo', name: 'Zoology' },
  { id: 'col-bot', name: 'Botany' },
  { id: 'col-arc', name: 'Archaeology' },
];

const ROWS: MockRow[] = [
  {
    collectionId: 'col-zoo',
    collectionName: 'Zoology',
    sourceDocumentId: 'doc-1',
    fileName: 'zoology-inventory.xlsx',
    sheet: 'Specimens',
    rowNumber: 2,
    cells: { 'Inventory No': 'ZOO-001', Taxon: 'Panthera onca', Collected: '1998-05-04' },
    highlight: '...<b>Panthera onca</b> collected 1998...',
    objectSnapshot: {
      inventoryNumber: 'ZOO-001',
      displayTitle: 'Panthera onca',
      objectName: 'Panthera onca',
      briefDescriptionSnapshot: '1998-05-04',
      category: 'Zoology',
    },
    content: 'ZOO-001 Panthera onca 1998-05-04',
  },
  {
    collectionId: 'col-zoo',
    collectionName: 'Zoology',
    sourceDocumentId: 'doc-1',
    fileName: 'zoology-inventory.xlsx',
    sheet: 'Specimens',
    rowNumber: 3,
    cells: { 'Inventory No': 'ZOO-002', Taxon: 'Ara ararauna' },
    highlight: '...<b>Ara ararauna</b>...',
    objectSnapshot: {
      inventoryNumber: 'ZOO-002',
      displayTitle: 'Ara ararauna',
      objectName: 'Ara ararauna',
      briefDescriptionSnapshot: null,
      category: 'Zoology',
    },
    content: 'ZOO-002 Ara ararauna',
  },
  {
    collectionId: 'col-bot',
    collectionName: 'Botany',
    sourceDocumentId: 'doc-2',
    fileName: 'botany-herbarium.xlsx',
    sheet: 'Herbarium',
    rowNumber: 2,
    cells: { Sample: 'BOT-009', Name: 'Quercus robur' },
    highlight: '...<b>Quercus robur</b>...',
    objectSnapshot: {
      inventoryNumber: 'BOT-009',
      displayTitle: 'Quercus robur',
      objectName: 'Quercus robur',
      briefDescriptionSnapshot: null,
      category: 'Botany',
    },
    content: 'BOT-009 Quercus robur',
  },
  {
    collectionId: 'col-arc',
    collectionName: 'Archaeology',
    sourceDocumentId: 'doc-3',
    fileName: 'excavation-site-12.xlsx',
    sheet: 'Findings',
    rowNumber: 5,
    cells: { Code: 'ARC-2024/0012', Description: 'Ceramic shard, site 12' },
    highlight: '...<b>ARC-2024/0012</b> ceramic shard...',
    objectSnapshot: null,
    content: 'ARC-2024/0012 Ceramic shard, site 12',
  },
];

@Injectable()
export class ObjectSearchServiceMock implements ObjectSearchApi {
  search(query: ObjectSearchQuery): Observable<ObjectSearchResult> {
    const q = query.q.trim().toLowerCase();
    const matches = ROWS.filter(
      (row) =>
        (!query.collectionId || row.collectionId === query.collectionId) &&
        row.content.toLowerCase().includes(q),
    );
    const start = query.page * query.size;
    const items = matches.slice(start, start + query.size).map((row) => {
      const { content, ...hit } = row;
      void content;
      return hit;
    });
    return of({ total: matches.length, page: query.page, size: query.size, items }).pipe(
      delay(300),
    );
  }

  listSearchableCollections(): Observable<SearchableCollection[]> {
    return of(COLLECTIONS).pipe(delay(150));
  }
}
