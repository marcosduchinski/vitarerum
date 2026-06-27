import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  resource,
  signal,
} from '@angular/core';
import { Router } from '@angular/router';
import { MenuItem } from 'primeng/api';
import { firstValueFrom } from 'rxjs';

import { IDENTITY_SERVICE } from '@core/auth/identity.service';
import { ApiError, toApiError } from '@core/http/api-error.model';
import { ConfirmModalComponent } from '@shared/components/confirm-modal/confirm-modal.component';
import { EmptyStateComponent } from '@shared/components/empty-state/empty-state.component';
import { ErrorMessageComponent } from '@shared/components/error-message/error-message.component';
import { LoadingStateComponent } from '@shared/components/loading-state/loading-state.component';
import { PageHeaderComponent } from '@shared/components/page-header/page-header.component';
import { RowActionsComponent } from '@shared/components/row-actions/row-actions.component';
import { UseType } from '@shared/models/collection-use-status.model';

import { CollectionUseProjectSummary } from '../../models/project.model';
import { PROJECT_API_SERVICE } from '../../services/project-api.service';
import { projectDetailRouteForGroup } from '../../utils/project-detail-route.util';

const PAGE_SIZE = 3;
const START_NOTE = 'Started from created projects awaiting start.';
const CANCEL_REASON = 'Cancelled from created projects awaiting start.';

const TYPE_LABELS: Record<UseType, string> = {
  EXHIBITION: 'Exhibition',
  IN_SITU_VISIT: 'In-situ visit',
  OTHER: 'Other',
};

@Component({
  selector: 'app-projects-pending-page',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    RowActionsComponent,
    PageHeaderComponent,
    LoadingStateComponent,
    ErrorMessageComponent,
    EmptyStateComponent,
    ConfirmModalComponent,
  ],
  templateUrl: './projects-pending-page.component.html',
  styleUrl: './projects-pending-page.component.scss',
})
export class ProjectsPendingPageComponent {
  private readonly projectService = inject(PROJECT_API_SERVICE);
  private readonly router = inject(Router);
  private readonly identity = inject(IDENTITY_SERVICE);

  protected readonly currentPage = signal(0);
  protected readonly searchDraft = signal('');
  protected readonly appliedSearch = signal('');
  protected readonly pageSize = PAGE_SIZE;

  // Refetch when the active role changes: requests carry X-Permission-Id.
  protected readonly currentPermissionId = computed(() => this.identity.getPermissionId());
  protected readonly isExternal = computed(() => this.identity.session()?.group === 'EXTERNAL');

  protected readonly projectsResource = resource({
    params: () => ({
      currentPermissionId: this.currentPermissionId(),
      page: this.currentPage(),
      size: this.pageSize,
      search: this.appliedSearch().trim(),
    }),
    loader: ({ params }) =>
      firstValueFrom(
        // A project only exists once its proposal is approved, so CREATED already
        // means "pending" — no proposal-approval filter is needed (or in the contract).
        this.projectService.listProjects({
          status: 'CREATED',
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
    this.totalProjects() === 0 ? 0 : this.currentPage() * this.pageSize + 1,
  );
  protected readonly rangeEnd = computed(() =>
    Math.min((this.currentPage() + 1) * this.pageSize, this.totalProjects()),
  );
  protected readonly listError = computed(() => {
    const err = this.projectsResource.error();
    return err ? toApiError(err) : null;
  });

  protected readonly actionProjectId = signal<string | null>(null);
  protected readonly actionError = signal<ApiError | null>(null);
  protected readonly cancelConfirmProjectId = signal<string | null>(null);
  protected readonly typeLabels = TYPE_LABELS;

  protected actionItemsFor(project: CollectionUseProjectSummary): MenuItem[] {
    const projectId = project.id;

    return [
      {
        label: 'Detail',
        icon: 'pi pi-eye',
        command: () => {
          void this.router.navigate(this.detailRoute(projectId), {
            queryParams: {
              returnTo: '/p/collections/projects/pending',
              returnLabel: 'pending projects',
            },
          });
        },
      },
      {
        label: 'Cancel',
        icon: 'pi pi-times',
        command: () => this.requestCancelConfirmation(projectId),
      },
    ];
  }

  protected requesterLabel(project: CollectionUseProjectSummary): string {
    return project.requestedBy?.user.name ?? 'Unknown requester';
  }

  private detailRoute(projectId: string): readonly string[] {
    return projectDetailRouteForGroup(projectId, this.identity.session()?.group);
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

  protected requestCancelConfirmation(projectId: string): void {
    if (this.actionProjectId()) return;
    this.cancelConfirmProjectId.set(projectId);
  }

  protected cancelCancelConfirmation(): void {
    this.cancelConfirmProjectId.set(null);
  }

  protected async start(projectId: string): Promise<void> {
    if (this.actionProjectId()) return;
    this.actionProjectId.set(projectId);
    this.actionError.set(null);

    try {
      await firstValueFrom(this.projectService.startProject(projectId, { note: START_NOTE }));
      this.projectsResource.reload();
    } catch (err) {
      this.actionError.set(toApiError(err));
    } finally {
      this.actionProjectId.set(null);
    }
  }

  protected async cancel(projectId: string): Promise<void> {
    if (this.actionProjectId()) return;
    this.actionProjectId.set(projectId);
    this.actionError.set(null);

    try {
      await firstValueFrom(this.projectService.cancelProject(projectId, { reason: CANCEL_REASON }));
      this.cancelConfirmProjectId.set(null);
      this.projectsResource.reload();
    } catch (err) {
      this.actionError.set(toApiError(err));
      this.cancelConfirmProjectId.set(null);
    } finally {
      this.actionProjectId.set(null);
    }
  }
}
