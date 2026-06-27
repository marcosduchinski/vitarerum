import { HttpClient } from '@angular/common/http';
import { inject, Injectable, InjectionToken } from '@angular/core';
import { API_BASE_URL } from '@core/config/app-config.model';
import { buildApiUrl } from '@core/http/api-url.util';
import { buildHttpParams } from '@core/http/http-params.util';
import { Group, GroupsResponse } from '@core/auth/models/group.model';
import {
  GroupMembership,
  UserPermissionsResponse,
} from '@core/auth/models/permission.model';
import { UserDetail } from '@core/auth/models/user.model';
import { Page, PageQuery } from '@shared/models/page.model';
import { Observable } from 'rxjs';

export interface UserListQuery extends PageQuery {
  readonly groupId?: string;
  readonly search?: string;
}

export interface GroupUsersPage extends Page<GroupMembership> {
  readonly group: Group;
}

export const USER_MANAGEMENT_SERVICE = new InjectionToken<UserManagementService>(
  'USER_MANAGEMENT_SERVICE',
);

@Injectable()
export class UserManagementService {
  private readonly http = inject(HttpClient);
  private readonly apiBaseUrl = inject(API_BASE_URL);

  listUsers(query: UserListQuery = {}): Observable<Page<UserDetail>> {
    return this.http.get<Page<UserDetail>>(this.url('/users'), {
      params: buildHttpParams(query),
    });
  }

  getUser(userId: string): Observable<UserDetail> {
    return this.http.get<UserDetail>(this.url(`/users/${userId}`));
  }

  assignGroup(userId: string, groupId: string): Observable<GroupMembership> {
    return this.http.post<GroupMembership>(this.url(`/users/${userId}/groups/${groupId}`), null);
  }

  revokeGroup(userId: string, groupId: string): Observable<void> {
    return this.http.delete<void>(this.url(`/users/${userId}/groups/${groupId}`));
  }

  listUserPermissions(userId: string): Observable<UserPermissionsResponse> {
    return this.http.get<UserPermissionsResponse>(this.url(`/users/${userId}/permissions`));
  }

  listGroups(): Observable<GroupsResponse> {
    return this.http.get<GroupsResponse>(this.url('/groups'));
  }

  listGroupUsers(groupId: string, query: PageQuery = {}): Observable<GroupUsersPage> {
    return this.http.get<GroupUsersPage>(this.url(`/groups/${groupId}/users`), {
      params: buildHttpParams(query),
    });
  }

  private url(path: string): string {
    return buildApiUrl(this.apiBaseUrl, path);
  }
}
