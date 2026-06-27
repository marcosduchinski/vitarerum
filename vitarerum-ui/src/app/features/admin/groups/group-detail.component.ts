import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  input,
  resource,
  signal,
} from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { MenuItem } from 'primeng/api';
import { ButtonDirective } from 'primeng/button';
import { USER_MANAGEMENT_SERVICE, GroupUsersPage } from '@features/admin/services/user-management.service';
import { GroupName } from '@core/auth/models/group-name.enum';
import { toApiError } from '@core/http/api-error.model';
import { ErrorMessageComponent } from '@shared/components/error-message/error-message.component';
import { LoadingStateComponent } from '@shared/components/loading-state/loading-state.component';
import { EmptyStateComponent } from '@shared/components/empty-state/empty-state.component';
import { RowActionsComponent } from '@shared/components/row-actions/row-actions.component';

const GROUP_META: Record<GroupName, { label: string; description: string }> = {
  EXTERNAL: {
    label: 'External researchers',
    description: 'Researchers who submit collection-use proposals and manage their own projects.',
  },
  COLLECTIONS_MANAGEMENT: {
    label: 'Collections management',
    description: 'Staff responsible for receiving proposals, requesting documents, and assigning work.',
  },
  CURATORIAL: {
    label: 'Curatorial',
    description: 'Curators who review proposals, contribute to project decisions, and add entries.',
  },
  DIRECTION: {
    label: 'Direction',
    description: 'Institutional direction that clarifies or decides on referred proposals.',
  },
  SYS_ADMIN: {
    label: 'Administrators',
    description: 'System administrators with full access to users, groups, proposals, and projects.',
  },
};

const PAGE_SIZE = 20;

@Component({
  selector: 'app-group-detail',
  standalone: true,
  imports: [
    RouterLink,
    RowActionsComponent,
    ButtonDirective,
    ErrorMessageComponent,
    LoadingStateComponent,
    EmptyStateComponent,
  ],
  templateUrl: './group-detail.component.html',
  styleUrl: './group-detail.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class GroupDetailComponent {
  private readonly userService = inject(USER_MANAGEMENT_SERVICE);
  private readonly router = inject(Router);

  readonly id = input.required<string>();

  protected readonly currentPage = signal(0);

  protected readonly membersResource = resource<GroupUsersPage, { groupId: string; page: number; size: number }>({
    params: () => ({ groupId: this.id(), page: this.currentPage(), size: PAGE_SIZE }),
    loader: ({ params }): Promise<GroupUsersPage> =>
      firstValueFrom(this.userService.listGroupUsers(params.groupId, { page: params.page, size: params.size })),
  });

  protected readonly apiError = computed(() => {
    const err = this.membersResource.error();
    return err ? toApiError(err) : null;
  });

  protected readonly group = computed(() => this.membersResource.value()?.group ?? null);
  protected readonly members = computed(() => this.membersResource.value()?.content ?? []);
  protected readonly totalMembers = computed(() => this.membersResource.value()?.totalElements ?? 0);
  protected readonly totalPages = computed(() => this.membersResource.value()?.totalPages ?? 0);

  protected readonly groupLabel = computed(() => {
    const g = this.group();
    return g ? (GROUP_META[g.name]?.label ?? g.name) : '';
  });

  protected readonly groupDescription = computed(() => {
    const g = this.group();
    return g ? (GROUP_META[g.name]?.description ?? '') : '';
  });

  protected readonly rangeStart = computed(() => this.currentPage() * PAGE_SIZE + 1);
  protected readonly rangeEnd = computed(() =>
    Math.min((this.currentPage() + 1) * PAGE_SIZE, this.totalMembers()),
  );

  protected actionItemsFor(userId: string): MenuItem[] {
    return [
      {
        label: 'Details',
        icon: 'pi pi-eye',
        command: () => {
          void this.router.navigate(['/p/admin/users', userId]);
        },
      },
    ];
  }

  protected prevPage(): void {
    this.currentPage.update(p => Math.max(0, p - 1));
  }

  protected nextPage(): void {
    this.currentPage.update(p => p + 1);
  }
}
