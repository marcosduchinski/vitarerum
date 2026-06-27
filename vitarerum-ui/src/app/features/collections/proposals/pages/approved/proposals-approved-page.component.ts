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
import { StatusChipComponent } from '@shared/components/status-chip/status-chip.component';
import { TypeChipComponent } from '@shared/components/type-chip/type-chip.component';

import { PROPOSAL_API_SERVICE } from '../../services/proposal-api.service';

const DEFAULT_PAGE_SIZE = 20;
const PAGE_SIZE_OPTIONS = [10, 20, 50, 100] as const;

@Component({
  selector: 'app-proposals-approved-page',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    RouterLink,
    RowActionsComponent,
    PageHeaderComponent,
    LoadingStateComponent,
    ErrorMessageComponent,
    EmptyStateComponent,
    StatusChipComponent,
    TypeChipComponent,
  ],
  templateUrl: './proposals-approved-page.component.html',
  styleUrl: './proposals-approved-page.component.scss',
})
export class ProposalsApprovedPageComponent {
  private readonly proposalService = inject(PROPOSAL_API_SERVICE);
  private readonly router = inject(Router);
  private readonly identity = inject(IDENTITY_SERVICE);

  protected readonly currentPage = signal(0);
  protected readonly pageSize = signal(DEFAULT_PAGE_SIZE);
  protected readonly searchDraft = signal('');
  protected readonly appliedSearch = signal('');

  // Refetch when the active role changes: requests carry X-Permission-Id.
  protected readonly currentPermissionId = computed(() => this.identity.getPermissionId());

  protected readonly proposalsResource = resource({
    params: () => ({
      currentPermissionId: this.currentPermissionId(),
      page: this.currentPage(),
      size: this.pageSize(),
      search: this.appliedSearch().trim(),
    }),
    loader: ({ params }) =>
      firstValueFrom(
        this.proposalService.listProposals({
          status: 'APPROVED',
          page: params.page,
          size: params.size,
          search: params.search,
        }),
      ),
  });

  protected readonly proposals = computed(() => this.proposalsResource.value()?.content ?? []);
  protected readonly totalProposals = computed(
    () => this.proposalsResource.value()?.totalElements ?? 0,
  );
  protected readonly totalPages = computed(() => this.proposalsResource.value()?.totalPages ?? 0);
  protected readonly rangeStart = computed(() =>
    this.totalProposals() === 0 ? 0 : this.currentPage() * this.pageSize() + 1,
  );
  protected readonly rangeEnd = computed(() =>
    Math.min((this.currentPage() + 1) * this.pageSize(), this.totalProposals()),
  );
  protected readonly listError = computed<ApiError | null>(() => {
    const err = this.proposalsResource.error();
    return err ? toApiError(err) : null;
  });

  protected readonly pageSizeOptions = PAGE_SIZE_OPTIONS;

  protected actionItemsFor(proposalId: string, projectId: string | null): MenuItem[] {
    const items: MenuItem[] = [
      {
        label: 'Details',
        icon: 'pi pi-eye',
        command: () => {
          void this.router.navigate(['/p/collections/proposals/approved', proposalId]);
        },
      },
    ];

    // The linked project is only present once the proposal is materialised.
    if (projectId) {
      items.push({
        label: 'Go to project',
        icon: 'pi pi-folder-open',
        command: () => {
          void this.router.navigate(['/p/collections/projects', projectId], {
            queryParams: {
              returnTo: '/p/collections/proposals/approved',
              returnLabel: 'approved proposals',
            },
          });
        },
      });
    }

    return items;
  }

  protected prevPage(): void {
    this.currentPage.update((page) => Math.max(0, page - 1));
  }

  protected nextPage(): void {
    this.currentPage.update((page) => Math.min(Math.max(0, this.totalPages() - 1), page + 1));
  }

  protected firstPage(): void {
    this.currentPage.set(0);
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
