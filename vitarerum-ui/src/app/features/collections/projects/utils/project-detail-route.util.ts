import { GroupName } from '@core/auth/models/group-name.enum';

const STAFF_DETAIL_ROUTE_PREFIX: Partial<Record<GroupName, readonly string[]>> = {
  COLLECTIONS_MANAGEMENT: ['/p/collections/projects/collections'],
  CURATORIAL: ['/p/collections/projects/curatorial'],
  DIRECTION: ['/p/collections/projects/direction'],
};

export function projectDetailRouteForGroup(
  projectId: string,
  group: GroupName | null | undefined,
): readonly string[] {
  const prefix = group ? STAFF_DETAIL_ROUTE_PREFIX[group] : undefined;
  return [...(prefix ?? ['/p/collections/projects']), projectId];
}
