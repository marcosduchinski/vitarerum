/** Collection Data Sources management models (admin area).
 * A "collection" here is a curated scientific collection (Zoology, Botany, ...)
 * whose staff-uploaded .xlsx files feed the searchable object index. */

export type SourceDocumentStatus = 'UPLOADED' | 'INDEXED' | 'ERROR';

export interface CollectionCurator {
  readonly permissionId: string;
  readonly name: string | null;
  readonly email: string | null;
  readonly assignedAt: string;
}

/** A scientific/administrative classification above `Collection` (e.g.
 * Natural History groups Botany, Zoology, ...). Catalogue organisation
 * only — curators and documents stay at the `Collection` level. */
export interface CollectionArea {
  readonly id: string;
  readonly name: string;
  readonly collectionCount: number;
}

export interface CollectionDataSource {
  readonly id: string;
  readonly areaId: string;
  readonly areaName: string;
  readonly name: string;
  readonly curators: readonly CollectionCurator[];
  readonly documentCount: number;
  /** Whether the caller may manage this collection (server-decided). */
  readonly manageable: boolean;
}

export interface SourceDocument {
  readonly id: string;
  readonly collectionId: string;
  readonly fileName: string;
  readonly sourceKind: string;
  readonly status: SourceDocumentStatus;
  readonly errorMessage: string | null;
  readonly rowCount: number | null;
  readonly uploadedAt: string;
  readonly indexedAt: string | null;
  readonly contentMatchesSearchableColumns: boolean;
  readonly objectMapping: SourceDocumentObjectMapping | null;
}

export interface UpdateCollectionRequest {
  readonly name: string;
}

export interface SourceDocumentObjectMapping {
  readonly inventoryNumberColumn: string;
  readonly displayTitleColumn: string;
  readonly displayTitleColumns?: readonly string[];
  readonly objectNameColumn: string | null;
  readonly descriptionColumns: readonly string[];
  readonly searchableColumns: readonly string[];
}

export interface UpdateSourceDocumentObjectMappingRequest {
  readonly inventoryNumberColumn: string;
  readonly displayTitleColumns: readonly string[];
  readonly objectNameColumn: string | null;
  readonly descriptionColumns: readonly string[];
  readonly searchableColumns: readonly string[];
}

/** A permission in the CURATORIAL group, eligible to be assigned as a curator. */
export interface CuratorCandidate {
  readonly permissionId: string;
  readonly name: string;
  readonly email: string;
}
