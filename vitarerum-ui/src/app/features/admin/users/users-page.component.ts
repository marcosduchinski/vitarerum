import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  resource,
  signal,
} from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { MenuItem } from 'primeng/api';
import { InputText } from 'primeng/inputtext';
import { ButtonDirective } from 'primeng/button';
import { toApiError } from '@core/http/api-error.model';
import { USER_MANAGEMENT_SERVICE } from '@features/admin/services/user-management.service';
import { GroupName } from '@core/auth/models/group-name.enum';
import { groupNameOf } from '@core/auth/models/permission.model';
import { UserDetail } from '@core/auth/models/user.model';
import { Page } from '@shared/models/page.model';
import { AvatarComponent } from '@shared/components/avatar/avatar.component';
import { DataTableComponent } from '@shared/components/data-table/data-table.component';
import { ErrorMessageComponent } from '@shared/components/error-message/error-message.component';
import { LoadingStateComponent } from '@shared/components/loading-state/loading-state.component';
import { EmptyStateComponent } from '@shared/components/empty-state/empty-state.component';
import { PageHeaderComponent } from '@shared/components/page-header/page-header.component';
import { PaginationComponent } from '@shared/components/pagination/pagination.component';
import { RoleChipComponent } from '@shared/components/role-chip/role-chip.component';
import { RowActionsComponent } from '@shared/components/row-actions/row-actions.component';

const PAGE_SIZE = 20;

@Component({
  selector: 'app-users-page',
  standalone: true,
  imports: [
    RouterLink,
    RowActionsComponent,
    InputText,
    ButtonDirective,
    AvatarComponent,
    DataTableComponent,
    ErrorMessageComponent,
    LoadingStateComponent,
    EmptyStateComponent,
    PageHeaderComponent,
    PaginationComponent,
    RoleChipComponent,
  ],
  templateUrl: './users-page.component.html',
  styleUrl: './users-page.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class UsersPageComponent {
  private readonly userService = inject(USER_MANAGEMENT_SERVICE);
  private readonly router = inject(Router);

  protected readonly searchQuery = signal('');
  protected readonly currentPage = signal(0);

  protected readonly usersResource = resource<Page<UserDetail>, { search?: string; page: number; size: number }>({
    params: () => ({
      search: this.searchQuery() || undefined,
      page: this.currentPage(),
      size: PAGE_SIZE,
    }),
    loader: ({ params }): Promise<Page<UserDetail>> => firstValueFrom(this.userService.listUsers(params)),
  });

  protected readonly apiError = computed(() => {
    const err = this.usersResource.error();
    return err ? toApiError(err) : null;
  });

  protected readonly pageSize = PAGE_SIZE;
  protected readonly users = computed(() => this.usersResource.value()?.content ?? []);
  protected readonly totalUsers = computed(() => this.usersResource.value()?.totalElements ?? 0);
  protected readonly totalPages = computed(() => this.usersResource.value()?.totalPages ?? 0);

  // Normalises a permission's group (the backend may send a bare GroupName
  // string or a nested {id, name}) to a GroupName for chips/avatars.
  protected readonly groupNameOf = groupNameOf;

  protected primaryGroup(user: UserDetail): GroupName | undefined {
    const permission = user.permissions[0];
    return permission ? groupNameOf(permission.group) : undefined;
  }

  protected actionItemsFor(user: UserDetail): MenuItem[] {
    return [
      {
        label: 'Details',
        icon: 'pi pi-eye',
        command: () => {
          void this.router.navigate(['/p/admin/users', user.id]);
        },
      },
    ];
  }

  protected createUser(): void {
    void this.router.navigate(['/p/admin/users/new']);
  }

  protected onSearch(event: Event): void {
    this.searchQuery.set((event.target as HTMLInputElement).value);
    this.currentPage.set(0);
  }

  protected prevPage(): void {
    this.currentPage.update(p => Math.max(0, p - 1));
  }

  protected nextPage(): void {
    this.currentPage.update(p => Math.min(Math.max(0, this.totalPages() - 1), p + 1));
  }
}
