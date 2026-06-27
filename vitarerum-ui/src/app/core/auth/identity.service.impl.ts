import { computed, inject, Injectable, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { AuthApiService } from './auth-api.service';
import { IdentityService } from './identity.service';
import { GroupName } from './models/group-name.enum';
import { IdentitySession } from './models/identity-session.model';
import { LoginRequest } from './models/login.model';
import { clearSession, readSession, writeSession } from './session-storage.util';

@Injectable()
export class IdentityServiceImpl implements IdentityService {
  private readonly authApi = inject(AuthApiService);
  // Rehydrate from storage on construction so a page refresh keeps the session.
  private readonly sessionState = signal<IdentitySession | null>(readSession());

  readonly session = this.sessionState.asReadonly();
  readonly isAuthenticated = computed(() => this.session() !== null);
  readonly isStaff = computed(() => {
    const group = this.session()?.group;
    return group != null && group !== 'EXTERNAL';
  });

  async signIn(credentials: LoginRequest): Promise<void> {
    const response = await firstValueFrom(this.authApi.login(credentials));
    this.setSession({
      accessToken: response.accessToken,
      user: response.user,
      permissions: response.permissions,
      availableGroups: response.permissions.map((permission) => permission.group),
      group: response.permissions[0]?.group ?? null,
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

  // Available groups come from the login response; no client-side update needed.
  updateAvailableGroups(groups: readonly GroupName[]): void {
    void groups;
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
