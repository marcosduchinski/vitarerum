import { GroupName } from './group-name.enum';
import { IdentityUser } from './identity-user.model';

export interface SessionPermission {
  permissionId: string;
  group: GroupName;
}

export interface IdentitySession {
  accessToken: string;
  user: IdentityUser;
  group: GroupName | null;
  availableGroups: readonly GroupName[];
  // One permission id per group the principal belongs to. The active permission id
  // is the entry whose group matches the currently selected `group`.
  permissions?: readonly SessionPermission[];
}
