import { GroupName } from './group-name.enum';
import { Group } from './group.model';
import { User } from './user.model';

export interface PermissionSummary {
  readonly permissionId: string;
  readonly group: Group;
}

// Tolerates both permission group shapes a backend may send: the nested
// `{ id, name }` object (contract target) or a bare `GroupName` string.
export function groupNameOf(group: Group | GroupName): GroupName {
  return typeof group === 'string' ? group : group.name;
}

export interface PermissionPrincipal {
  readonly permissionId: string;
  readonly user: User;
  readonly group: GroupName;
}

export interface GroupMembership {
  readonly permissionId: string;
  readonly user: User;
  readonly group: Group;
}

export interface UserPermissionsResponse {
  readonly userId: string;
  readonly permissions: readonly PermissionSummary[];
}
