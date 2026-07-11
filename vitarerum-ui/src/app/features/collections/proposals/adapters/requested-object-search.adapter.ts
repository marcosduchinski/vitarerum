import { ObjectSearchHit } from '@features/objects/models/object-search.model';

import { AddRequestedObjectsRequest } from '../models/proposal-actions.model';

export type RequestedObjectSearchAdapterResult =
  | {
      readonly ok: true;
      readonly item: AddRequestedObjectsRequest['objects'][number];
    }
  | {
      readonly ok: false;
      readonly reason: string;
    };

export function adaptSearchHitToRequestedObject(
  hit: ObjectSearchHit,
): RequestedObjectSearchAdapterResult {
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
