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

export interface CollectionDataSource {
  readonly id: string;
  readonly name: string;
  readonly active: boolean;
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
}
