import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  resource,
  signal,
} from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { MenuItem } from 'primeng/api';
import { firstValueFrom } from 'rxjs';

import { IDENTITY_SERVICE } from '@core/auth/identity.service';
import { ApiError, toApiError } from '@core/http/api-error.model';
import { EmptyStateComponent } from '@shared/components/empty-state/empty-state.component';
import { ErrorMessageComponent } from '@shared/components/error-message/error-message.component';
import { LoadingStateComponent } from '@shared/components/loading-state/loading-state.component';
import { PageHeaderComponent } from '@shared/components/page-header/page-header.component';
import { RowActionsComponent } from '@shared/components/row-actions/row-actions.component';
import { UseType } from '@shared/models/collection-use-status.model';

import { CollectionUseProjectSummary } from '../../models/project.model';
import { PROJECT_API_SERVICE } from '../../services/project-api.service';
import { projectDetailRouteForGroup } from '../../utils/project-detail-route.util';

const DEFAULT_PAGE_SIZE = 20;
const PAGE_SIZE_OPTIONS = [10, 20, 50, 100] as const;

const TYPE_LABELS: Record<UseType, string> = {
  EXHIBITION: 'Exhibition',
  IN_SITU_VISIT: 'In-situ visit',
  OTHER: 'Other',
};

const DETAIL_QUERY_PARAMS = {
  returnTo: '/p/collections/projects/cancelled',
  returnLabel: 'cancelled projects',
} as const;

@Component({
  selector: 'app-projects-cancelled-page',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    RouterLink,
    RowActionsComponent,
    PageHeaderComponent,
    LoadingStateComponent,
    ErrorMessageComponent,
    EmptyStateComponent,
  ],
  templateUrl: './projects-cancelled-page.component.html',
  styleUrl: './projects-cancelled-page.component.scss',
})
export class ProjectsCancelledPageComponent {
  private readonly projectService = inject(PROJECT_API_SERVICE);
  private readonly identity = inject(IDENTITY_SERVICE);
  private readonly router = inject(Router);

  protected readonly currentPage = signal(0);
  protected readonly pageSize = signal(DEFAULT_PAGE_SIZE);
  protected readonly searchDraft = signal('');
  protected readonly appliedSearch = signal('');

  // Refetch when the active role changes: requests carry X-Permission-Id.
  protected readonly currentPermissionId = computed(() => this.identity.getPermissionId());

  protected readonly projectsResource = resource({
    params: () => ({
      currentPermissionId: this.currentPermissionId(),
      page: this.currentPage(),
      size: this.pageSize(),
      search: this.appliedSearch().trim(),
    }),
    loader: ({ params }) =>
      firstValueFrom(
        this.projectService.listProjects({
          status: 'CANCELLED',
          page: params.page,
          size: params.size,
          search: params.search,
        }),
      ),
  });

  protected readonly projects = computed(() => this.projectsResource.value()?.content ?? []);
  protected readonly totalProjects = computed(
    () => this.projectsResource.value()?.totalElements ?? 0,
  );
  protected readonly totalPages = computed(() => this.projectsResource.value()?.totalPages ?? 0);
  protected readonly rangeStart = computed(() =>
    this.totalProjects() === 0 ? 0 : this.currentPage() * this.pageSize() + 1,
  );
  protected readonly rangeEnd = computed(() =>
    Math.min((this.currentPage() + 1) * this.pageSize(), this.totalProjects()),
  );
  protected readonly listError = computed<ApiError | null>(() => {
    const err = this.projectsResource.error();
    return err ? toApiError(err) : null;
  });

  protected readonly typeLabels = TYPE_LABELS;
  protected readonly pageSizeOptions = PAGE_SIZE_OPTIONS;
  protected readonly detailQueryParams = DETAIL_QUERY_PARAMS;

  protected detailRoute(projectId: string): readonly string[] {
    return projectDetailRouteForGroup(projectId, this.identity.session()?.group);
  }

  protected actionItemsFor(project: CollectionUseProjectSummary): MenuItem[] {
    return [
      {
        label: 'Details',
        icon: 'pi pi-eye',
        command: () => {
          void this.router.navigate([...this.detailRoute(project.id)], {
            queryParams: this.detailQueryParams,
          });
        },
      },
    ];
  }

  protected requesterLabel(project: CollectionUseProjectSummary): string {
    return project.requestedBy?.user.name ?? 'Unknown requester';
  }

  protected requesterEmail(project: CollectionUseProjectSummary): string {
    return project.requestedBy?.user.email ?? '';
  }

  protected assigneeLabel(project: CollectionUseProjectSummary): string {
    return project.proposal.assignedTo?.user.name ?? 'Unassigned';
  }

  protected assigneeEmail(project: CollectionUseProjectSummary): string {
    return project.proposal.assignedTo?.user.email ?? '';
  }

  protected dateLabel(date: string): string {
    return date.slice(0, 10);
  }

  protected firstPage(): void {
    this.currentPage.set(0);
  }

  protected prevPage(): void {
    this.currentPage.update((page) => Math.max(0, page - 1));
  }

  protected nextPage(): void {
    this.currentPage.update((page) => Math.min(Math.max(0, this.totalPages() - 1), page + 1));
  }

  protected lastPage(): void {
    this.currentPage.set(Math.max(0, this.totalPages() - 1));
  }

  protected onPageSizeChange(event: Event): void {
    this.pageSize.set(Number((event.target as HTMLSelectElement).value));
    this.currentPage.set(0);
  }

  protected onSearchInput(event: Event): void {
    this.searchDraft.set((event.target as HTMLInputElement).value);
  }

  protected applySearch(): void {
    this.appliedSearch.set(this.searchDraft().trim());
    this.currentPage.set(0);
  }

  protected clearSearch(): void {
    this.searchDraft.set('');
    this.appliedSearch.set('');
    this.currentPage.set(0);
  }
}
