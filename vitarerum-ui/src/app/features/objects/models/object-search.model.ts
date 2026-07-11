/** Objects -> Search models. A "collection" is a curated scientific
 * collection (Zoology, Botany, ...); a hit is one indexed spreadsheet row. */

export interface SearchableCollection {
  readonly id: string;
  readonly name: string;
}

export interface ObjectSearchHit {
  readonly collectionId: string;
  readonly collectionName: string;
  readonly sourceDocumentId: string;
  readonly fileName: string;
  readonly sheet: string;
  readonly rowNumber: number;
  readonly cells: Record<string, string>;
  readonly highlight: string;
  readonly objectSnapshot: ObjectSearchSnapshot | null;
}

export interface ObjectSearchSnapshot {
  readonly inventoryNumber: string;
  readonly displayTitle: string;
  readonly objectName: string;
  readonly briefDescriptionSnapshot: string | null;
  readonly category: string;
}

export interface ObjectSearchResult {
  readonly total: number;
  readonly page: number;
  readonly size: number;
  readonly items: readonly ObjectSearchHit[];
}

export interface ObjectSearchQuery {
  readonly q: string;
  readonly collectionId?: string;
  readonly page: number;
  readonly size: number;
}
