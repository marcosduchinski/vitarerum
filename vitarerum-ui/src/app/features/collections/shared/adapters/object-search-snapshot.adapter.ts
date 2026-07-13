import { ObjectSearchHit } from '@features/objects/models/object-search.model';

export interface ObjectSearchSnapshot {
  readonly inventoryNumber: string;
  readonly displayTitle: string;
  readonly objectName: string;
  readonly briefDescriptionSnapshot?: string | null;
  readonly category?: string;
  readonly description?: string;
}

export type ObjectSearchSnapshotAdapterResult =
  | {
      readonly ok: true;
      readonly item: ObjectSearchSnapshot;
    }
  | {
      readonly ok: false;
      readonly reason: string;
    };

export function adaptSearchHitToObjectSnapshot(
  hit: ObjectSearchHit,
): ObjectSearchSnapshotAdapterResult {
  const snapshot = hit.objectSnapshot;
  if (!snapshot) {
    return {
      ok: false,
      reason: 'Cannot add this row: missing inventory/title/name mapping.',
    };
  }
  if (!snapshot.inventoryNumber || !snapshot.displayTitle || !snapshot.objectName) {
    return {
      ok: false,
      reason: 'Cannot add this row: missing inventory/title/name mapping.',
    };
  }
  return {
    ok: true,
    item: {
      inventoryNumber: snapshot.inventoryNumber,
      displayTitle: snapshot.displayTitle,
      objectName: snapshot.objectName,
      briefDescriptionSnapshot: snapshot.briefDescriptionSnapshot,
      category: snapshot.category,
      description: `${hit.collectionName} / ${hit.fileName} / ${hit.sheet} row ${hit.rowNumber}`,
    },
  };
}
