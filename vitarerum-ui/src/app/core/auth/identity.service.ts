import { InjectionToken, Signal } from '@angular/core';

import { GroupName } from './models/group-name.enum';
import { IdentitySession } from './models/identity-session.model';
import { LoginRequest } from './models/login.model';

export interface IdentityService {
  readonly session: Signal<IdentitySession | null>;
  readonly isAuthenticated: Signal<boolean>;
  // True when the active group is a staff group (any group other than EXTERNAL).
  // Single source of truth for the staff/researcher distinction used by guards
  // and role-aware UI.
  readonly isStaff: Signal<boolean>;
  signIn(credentials: LoginRequest): Promise<void>;
  signOut(): void;
  getAccessToken(): string | null;
  getPermissionId(): string | null;
  setGroup(group: GroupName): void;
  updateAvailableGroups(groups: readonly GroupName[]): void;
}

export const IDENTITY_SERVICE = new InjectionToken<IdentityService>('IDENTITY_SERVICE');
