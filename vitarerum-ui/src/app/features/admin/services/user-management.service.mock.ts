import { inject, Injectable } from '@angular/core';
import { GroupsResponse } from '@core/auth/models/group.model';
import { IDENTITY_SERVICE } from '@core/auth/identity.service';
import { GroupName } from '@core/auth/models/group-name.enum';
import { GroupMembership, UserPermissionsResponse } from '@core/auth/models/permission.model';
import { UserDetail } from '@core/auth/models/user.model';
import { makePageFrom, MOCK_GROUPS, MOCK_MEMBERSHIPS, MOCK_USERS } from '../../collections/proposals/mocks/mock-data';
import { Page, PageQuery } from '@shared/models/page.model';
import { Observable, of, throwError } from 'rxjs';

import { GroupUsersPage, UserListQuery } from './user-management.service';

@Injectable()
export class UserManagementServiceMock {
  private readonly identity = inject(IDENTITY_SERVICE);
  private readonly users: UserDetail[] = structuredClone(MOCK_USERS);
  private readonly memberships: GroupMembership[] = structuredClone(MOCK_MEMBERSHIPS);

  listUsers(query: UserListQuery = {}): Observable<Page<UserDetail>> {
    let items = [...this.users];
    if (query.groupId) {
      const memberIds = this.memberships
        .filter(m => m.group.id === query.groupId)
        .map(m => m.user.id);
      items = items.filter(u => memberIds.includes(u.id));
    }
    if (query.search) {
      const q = query.search.toLowerCase();
      items = items.filter(u => u.name.toLowerCase().includes(q) || u.email.toLowerCase().includes(q));
    }
    return of(makePageFrom(items, query));
  }

  getUser(userId: string): Observable<UserDetail> {
    const user = this.users.find(u => u.id === userId);
    if (!user) return throwError(() => ({ status: 404, error: 'NOT_FOUND' }));
    return of(user);
  }

  assignGroup(userId: string, groupId: string): Observable<GroupMembership> {
    const user = this.users.find(u => u.id === userId);
    const group = MOCK_GROUPS.find(g => g.id === groupId);
    if (!user || !group) return throwError(() => ({ status: 404, error: 'NOT_FOUND' }));
    const existing = this.memberships.find(m => m.user.id === userId && m.group.id === groupId);
    if (existing) return of(existing);
    const membership: GroupMembership = {
      permissionId: `perm-${userId}-${groupId}`,
      user: { id: user.id, name: user.name, email: user.email },
      group,
    };
    this.memberships.push(membership);
    const idx = this.users.findIndex(u => u.id === userId);
    this.users[idx] = {
      ...user,
      permissions: [...user.permissions, { permissionId: membership.permissionId, group }],
    };
    this.syncSessionIfCurrentUser(userId);
    return of(membership);
  }

  revokeGroup(userId: string, groupId: string): Observable<void> {
    const idx = this.memberships.findIndex(m => m.user.id === userId && m.group.id === groupId);
    if (idx === -1) return throwError(() => ({ status: 404, error: 'NOT_FOUND' }));
    const permId = this.memberships[idx].permissionId;
    this.memberships.splice(idx, 1);
    const uIdx = this.users.findIndex(u => u.id === userId);
    if (uIdx !== -1) {
      this.users[uIdx] = {
        ...this.users[uIdx],
        permissions: this.users[uIdx].permissions.filter(p => p.permissionId !== permId),
      };
    }
    this.syncSessionIfCurrentUser(userId);
    return of(undefined);
  }

  listUserPermissions(userId: string): Observable<UserPermissionsResponse> {
    const user = this.users.find(u => u.id === userId);
    if (!user) return throwError(() => ({ status: 404, error: 'NOT_FOUND' }));
    return of({ userId, permissions: user.permissions });
  }

  listGroups(): Observable<GroupsResponse> {
    return of({ groups: MOCK_GROUPS });
  }

  listGroupUsers(groupId: string, query: PageQuery = {}): Observable<GroupUsersPage> {
    const group = MOCK_GROUPS.find(g => g.id === groupId);
    if (!group) return throwError(() => ({ status: 404, error: 'NOT_FOUND' }));
    const members = this.memberships.filter(m => m.group.id === groupId);
    return of({ ...makePageFrom(members, query), group });
  }

  private syncSessionIfCurrentUser(userId: string): void {
    if (this.identity.session()?.user.id !== userId) return;
    const user = this.users.find(u => u.id === userId);
    if (!user) return;
    const groups = user.permissions.map(p => p.group.name as GroupName);
    this.identity.updateAvailableGroups(groups);
  }
}
