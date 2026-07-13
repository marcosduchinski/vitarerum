import { ObjectSearchHit } from '@features/objects/models/object-search.model';

import { adaptSearchHitToObjectSnapshot } from '../../shared/adapters/object-search-snapshot.adapter';
import { AddProjectObjectsRequest } from '../models/project.model';

export type ProjectObjectSearchAdapterResult =
  | {
      readonly ok: true;
      readonly item: AddProjectObjectsRequest['objects'][number];
    }
  | {
      readonly ok: false;
      readonly reason: string;
    };

export function adaptSearchHitToProjectObject(
  hit: ObjectSearchHit,
): ProjectObjectSearchAdapterResult {
  const result = adaptSearchHitToObjectSnapshot(hit);
  return result.ok ? { ok: true, item: result.item } : result;
}
