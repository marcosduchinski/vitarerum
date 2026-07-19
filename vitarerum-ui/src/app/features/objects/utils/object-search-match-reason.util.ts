import { ObjectSearchHit, ObjectSearchMatchReason } from '../models/object-search.model';

export function primaryObjectSearchMatchReason(
  hit: ObjectSearchHit,
): ObjectSearchMatchReason | null {
  return hit.matchReasons?.[0] ?? null;
}

export function objectSearchMatchReasonText(hit: ObjectSearchHit): string {
  const reason = primaryObjectSearchMatchReason(hit);
  if (!reason) return 'Matched by automatic search';
  const columns = reason.columns?.filter(Boolean) ?? [];
  return columns.length
    ? `Matched by ${reason.label} - ${columns.join(', ')}`
    : `Matched by ${reason.label}`;
}

export function objectSearchMatchReasonClass(hit: ObjectSearchHit, baseClass: string): string {
  const method = primaryObjectSearchMatchReason(hit)?.method ?? 'automatic';
  return `${baseClass} ${baseClass}--${method}`;
}
