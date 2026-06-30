import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  input,
  resource,
  signal,
} from '@angular/core';
import { RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { ButtonDirective } from 'primeng/button';
import { toApiError, ApiError } from '@core/http/api-error.model';
import { USER_MANAGEMENT_SERVICE } from '@features/admin/services/user-management.service';
import { GroupName } from '@core/auth/models/group-name.enum';
import { GroupsResponse } from '@core/auth/models/group.model';
import { groupNameOf, PermissionSummary } from '@core/auth/models/permission.model';
import { UserDetail } from '@core/auth/models/user.model';
import { ErrorMessageComponent } from '@shared/components/error-message/error-message.component';
import { LoadingStateComponent } from '@shared/components/loading-state/loading-state.component';
import { ConfirmActionComponent } from '@shared/components/confirm-action/confirm-action.component';
import { PageHeaderComponent } from '@shared/components/page-header/page-header.component';
import { RoleChipComponent } from '@shared/components/role-chip/role-chip.component';

const GROUP_LABELS: Record<GroupName, string> = {
  EXTERNAL: 'External researcher',
  COLLECTIONS_MANAGEMENT: 'Collections management',
  CURATORIAL: 'Curatorial',
  DIRECTION: 'Direction',
  SYS_ADMIN: 'Administrator',
};

@Component({
  selector: 'app-user-detail',
  standalone: true,
  imports: [
    RouterLink,
    ButtonDirective,
    ErrorMessageComponent,
    LoadingStateComponent,
    ConfirmActionComponent,
    PageHeaderComponent,
    RoleChipComponent,
  ],
  templateUrl: './user-detail.component.html',
  styleUrl: './user-detail.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class UserDetailComponent {
  private readonly userService = inject(USER_MANAGEMENT_SERVICE);

  readonly id = input.required<string>();

  protected readonly userResource = resource<UserDetail, string>({
    params: () => this.id(),
    loader: ({ params: userId }): Promise<UserDetail> => firstValueFrom(this.userService.getUser(userId)),
  });

  protected readonly groupsResource = resource<GroupsResponse, undefined>({
    loader: (): Promise<GroupsResponse> => firstValueFrom(this.userService.listGroups()),
  });

  protected readonly userApiError = computed(() => {
    const err = this.userResource.error();
    return err ? toApiError(err) : null;
  });

  protected readonly user = computed(() => this.userResource.value() ?? null);

  protected readonly availableGroups = computed(() => {
    const u = this.user();
    const allGroups = this.groupsResource.value()?.groups ?? [];
    if (!u) return allGroups;
    // Match on group name, not id: the API serialises a permission's group as a
    // bare GroupName (no id), so ids can't be compared reliably.
    const assigned = new Set(u.permissions.map(p => groupNameOf(p.group)));
    return allGroups.filter(g => !assigned.has(g.name));
  });

  protected readonly selectedGroupId = signal('');
  protected readonly assignPending = signal(false);
  protected readonly assignError = signal<ApiError | null>(null);

  protected readonly revokeTarget = signal<PermissionSummary | null>(null);
  protected readonly revokePending = signal(false);
  protected readonly revokeError = signal<ApiError | null>(null);

  protected readonly groupLabels = GROUP_LABELS;
  // The backend may send a permission's group as a bare GroupName string or a
  // nested {id, name}; normalise before display/lookup.
  protected readonly groupNameOf = groupNameOf;

  /** Resolve a permission's group to its id via the loaded group directory.
   * Revoke is keyed by group id, but the API only sends the group's name on a
   * permission, so we look the id up from the (id-bearing) groups list. */
  private groupIdFor(group: PermissionSummary['group']): string | undefined {
    const name = groupNameOf(group);
    return this.groupsResource.value()?.groups.find(g => g.name === name)?.id;
  }

  protected onGroupSelect(event: Event): void {
    this.selectedGroupId.set((event.target as HTMLSelectElement).value);
  }

  protected async assignGroup(): Promise<void> {
    const groupId = this.selectedGroupId();
    const userId = this.id();
    if (!groupId) return;

    this.assignPending.set(true);
    this.assignError.set(null);

    try {
      await firstValueFrom(this.userService.assignGroup(userId, groupId));
      this.selectedGroupId.set('');
      this.userResource.reload();
    } catch (err) {
      this.assignError.set(toApiError(err));
    } finally {
      this.assignPending.set(false);
    }
  }

  protected requestRevoke(perm: PermissionSummary): void {
    this.revokeError.set(null);
    this.revokeTarget.set(perm);
  }

  protected cancelRevoke(): void {
    this.revokeTarget.set(null);
  }

  protected async confirmRevoke(): Promise<void> {
    const target = this.revokeTarget();
    if (!target) return;

    const groupId = this.groupIdFor(target.group);
    if (!groupId) {
      // The group directory hasn't resolved (or the group vanished); surface a
      // generic error rather than calling the API with an undefined id.
      this.revokeError.set(toApiError(null));
      this.revokeTarget.set(null);
      return;
    }

    this.revokePending.set(true);
    this.revokeError.set(null);

    try {
      await firstValueFrom(this.userService.revokeGroup(this.id(), groupId));
      this.revokeTarget.set(null);
      this.userResource.reload();
    } catch (err) {
      this.revokeError.set(toApiError(err));
      this.revokeTarget.set(null);
    } finally {
      this.revokePending.set(false);
    }
  }
}
