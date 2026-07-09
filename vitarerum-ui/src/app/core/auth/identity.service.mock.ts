import { computed, Injectable, signal } from '@angular/core';

import { IdentityService } from './identity.service';
import { GroupName } from './models/group-name.enum';
import {
  IdentitySession,
  SessionInstitution,
  SessionPermission,
} from './models/identity-session.model';
import { LoginRequest } from './models/login.model';
import {
  ChangePasswordRequest,
  PasswordResetConfirmRequest,
  PasswordResetRequest,
} from './models/password.model';
import { md5 } from './mock-password.util';
import { clearSession, readSession, writeSession } from './session-storage.util';

const MOCK_PASSWORD_DIGEST = '8b2c0b896b3a84c678d505cb1c6c5615';

interface MockAccount {
  readonly id: string;
  readonly name: string;
  readonly groups: readonly GroupName[];
}

const MOCK_PERMISSION_IDS_BY_USER_ID: Record<string, Partial<Record<GroupName, string>>> = {
  'u-alice': { EXTERNAL: 'perm-alice' },
  'u-bob': { COLLECTIONS_MANAGEMENT: 'perm-bob' },
  'u-carol': { CURATORIAL: 'perm-carol' },
  'u-dan': { DIRECTION: 'perm-dan' },
  'u-eve': { SYS_ADMIN: 'perm-eve' },
  'u-fran': {
    COLLECTIONS_MANAGEMENT: 'perm-fran-collections',
    CURATORIAL: 'perm-fran-curatorial',
    DIRECTION: 'perm-fran-direction',
  },
  'u-greg': { COLLECTIONS_MANAGEMENT: 'perm-greg' },
  'u-hugo': { EXTERNAL: 'perm-hugo' },
};

function mockPermissions(accountId: string, groups: readonly GroupName[]): SessionPermission[] {
  return groups.map((group) => ({
    permissionId:
      MOCK_PERMISSION_IDS_BY_USER_ID[accountId]?.[group] ?? `perm-${accountId}-${group}`,
    group,
  }));
}

const MOCK_ACCOUNTS: Record<string, MockAccount> = {
  'alice@ext.example.com': { id: 'u-alice', name: 'Alice Ferreira', groups: ['EXTERNAL'] },
  'bob@collections.example.com': {
    id: 'u-bob',
    name: 'Bob Santos',
    groups: ['COLLECTIONS_MANAGEMENT'],
  },
  'carol@curatorial.example.com': { id: 'u-carol', name: 'Carol Souza', groups: ['CURATORIAL'] },
  'dan@direction.example.com': { id: 'u-dan', name: 'Dan Oliveira', groups: ['DIRECTION'] },
  'eve@admin.example.com': { id: 'u-eve', name: 'Eve Lima', groups: ['SYS_ADMIN'] },
  'fran@staff.example.com': {
    id: 'u-fran',
    name: 'Fran Costa',
    groups: ['COLLECTIONS_MANAGEMENT', 'CURATORIAL', 'DIRECTION'],
  },
  'greg@collections.example.com': {
    id: 'u-greg',
    name: 'Greg Viana',
    groups: ['COLLECTIONS_MANAGEMENT'],
  },
  // Spans all three audiences (external / staff / admin) so the topbar role
  // switcher can be exercised across every menu + landing transition in dev.
  'hugo@mixed.example.com': {
    id: 'u-hugo',
    name: 'Hugo Prado',
    groups: ['EXTERNAL', 'COLLECTIONS_MANAGEMENT', 'SYS_ADMIN'],
  },
};

const UNKNOWN_ACCOUNT: MockAccount = { id: 'mock-user', name: '', groups: ['EXTERNAL'] };

const MOCK_INSTITUTION: SessionInstitution = {
  id: 'inst-muhnac',
  name: 'MUHNAC - Museu Nacional de História Natural e da Ciência de Lisboa',
};

@Injectable()
export class IdentityServiceMock implements IdentityService {
  private readonly sessionState = signal<IdentitySession | null>(readSession());
  // Every mock account shares one password (DEFAULT_PASSWORD in e2e/support/auth.ts).
  // Mutable so change/reset flows can be exercised end-to-end in mock mode.
  private passwordDigest = MOCK_PASSWORD_DIGEST;

  readonly session = this.sessionState.asReadonly();
  readonly isAuthenticated = computed(() => this.session() !== null);
  readonly isStaff = computed(() => {
    const group = this.session()?.group;
    return group != null && group !== 'EXTERNAL';
  });

  async signIn(credentials: LoginRequest): Promise<void> {
    if (md5(credentials.password) !== this.passwordDigest) {
      throw new Error('Invalid mock credentials');
    }

    const { email } = credentials;
    const account = MOCK_ACCOUNTS[email] ?? UNKNOWN_ACCOUNT;
    const availableGroups = account.groups;
    this.setSession({
      accessToken: 'mock-access-token',
      user: {
        id: account.id,
        email,
        displayName: account.name || email.split('@')[0] || 'Learning User',
      },
      group: availableGroups[0],
      availableGroups,
      permissions: mockPermissions(account.id, availableGroups),
      institution: MOCK_INSTITUTION,
    });
  }

  signOut(): void {
    this.setSession(null);
  }

  getAccessToken(): string | null {
    return this.session()?.accessToken ?? null;
  }

  getPermissionId(): string | null {
    const session = this.session();
    if (session === null) {
      return null;
    }

    return session.permissions?.find((p) => p.group === session.group)?.permissionId ?? null;
  }

  setGroup(group: GroupName): void {
    const session = this.session();
    if (session && session.availableGroups.includes(group)) {
      this.setSession({ ...session, group });
    }
  }

  updateAvailableGroups(groups: readonly GroupName[]): void {
    const session = this.session();
    if (!session) return;
    // Keep current group if still in the new list, otherwise switch to first available
    const group = groups.includes(session.group as GroupName) ? session.group : (groups[0] ?? null);
    this.setSession({
      ...session,
      group,
      availableGroups: groups,
      permissions: mockPermissions(session.user.id, groups),
    });
  }

  async changePassword(payload: ChangePasswordRequest): Promise<void> {
    if (md5(payload.currentPassword) !== this.passwordDigest) {
      throw new Error('Incorrect current password');
    }
    this.passwordDigest = md5(payload.newPassword);
  }

  // Always succeeds, known or unknown email — mirrors the backend's
  // anti-enumeration contract (see plano-gestao-passwords.md).
  async requestPasswordReset(_payload: PasswordResetRequest): Promise<void> {
    void _payload;
  }

  // Any (non-empty) token is accepted in mock mode; there's no real token
  // store to validate against.
  async confirmPasswordReset(payload: PasswordResetConfirmRequest): Promise<void> {
    this.passwordDigest = md5(payload.newPassword);
  }

  private setSession(session: IdentitySession | null): void {
    this.sessionState.set(session);
    if (session === null) {
      clearSession();
    } else {
      writeSession(session);
    }
  }
}
