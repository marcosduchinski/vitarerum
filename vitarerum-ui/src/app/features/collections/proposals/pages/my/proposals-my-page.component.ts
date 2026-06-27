import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  linkedSignal,
  resource,
  signal,
} from '@angular/core';
import { Router, RouterLink } from '@angular/router';
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
import { StatusChipComponent } from '@shared/components/status-chip/status-chip.component';
import { TypeChipComponent } from '@shared/components/type-chip/type-chip.component';
import { ProposalStatus } from '@shared/models/collection-use-status.model';
import { Page } from '@shared/models/page.model';

import { ProposalSummary } from '../../models/proposal.model';
import { PROPOSAL_API_SERVICE } from '../../services/proposal-api.service';

const DEFAULT_PAGE_SIZE = 20;
const PAGE_SIZE_OPTIONS = [10, 20, 50, 100] as const;
// Cancellation is allowed from these statuses; REJECTED/CANCELLED are terminal.
const CANCELLABLE_STATUSES: readonly ProposalStatus[] = ['SUBMITTED', 'PENDING', 'APPROVED'];

function emptyProposalPage(page: number, size: number): Page<ProposalSummary> {
  return { content: [], page, size, totalElements: 0, totalPages: 0 };
}

@Component({
  selector: 'app-proposals-my-page',
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
    ConfirmModalComponent,
  ],
  templateUrl: './proposals-my-page.component.html',
  styleUrl: './proposals-my-page.component.scss',
})
export class ProposalsMyPageComponent {
  private readonly identity = inject(IDENTITY_SERVICE);
  private readonly proposalService = inject(PROPOSAL_API_SERVICE);
  private readonly router = inject(Router);

  protected readonly currentPage = signal(0);
  protected readonly pageSize = signal(DEFAULT_PAGE_SIZE);
  protected readonly searchDraft = signal('');
  protected readonly appliedSearch = signal('');

  protected readonly currentPermissionId = computed(() => this.identity.getPermissionId());

  protected readonly proposalsResource = resource({
    params: () => ({
      page: this.currentPage(),
      size: this.pageSize(),
      search: this.appliedSearch().trim(),
      currentPermissionId: this.currentPermissionId(),
    }),
    loader: ({ params }) => {
      if (!params.currentPermissionId) {
        return Promise.resolve(emptyProposalPage(params.page, params.size));
      }

      return firstValueFrom(
        this.proposalService.listProposals({
          requestedBy: params.currentPermissionId,
          page: params.page,
          size: params.size,
          search: params.search,
        }),
      );
    },
  });

  // The resource clears value() to undefined whenever params change (every page
  // navigation), which would otherwise blank the whole list + pagination on each
  // Next/Prev click. Retain the last resolved page so the table stays mounted and
  // only the very first load shows the full-panel spinner.
  protected readonly loadedPage = linkedSignal<
    Page<ProposalSummary> | undefined,
    Page<ProposalSummary> | undefined
  >({
    source: () => this.proposalsResource.value(),
    computation: (value, previous) => value ?? previous?.value,
  });

  protected readonly initialLoading = computed(
    () => this.proposalsResource.isLoading() && !this.loadedPage(),
  );
  protected readonly reloading = computed(
    () => this.proposalsResource.isLoading() && !!this.loadedPage(),
  );

  protected readonly proposals = computed(() => this.loadedPage()?.content ?? []);
  protected readonly totalProposals = computed(() => this.loadedPage()?.totalElements ?? 0);
  protected readonly totalPages = computed(() => this.loadedPage()?.totalPages ?? 0);
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

  protected actionItemsFor(proposal: ProposalSummary): MenuItem[] {
    const items: MenuItem[] = [
      {
        label: 'Details',
        icon: 'pi pi-eye',
        command: () => {
          void this.router.navigate(['/p/collections/proposals', proposal.id], {
            queryParams: {
              returnTo: '/p/collections/proposals/my',
              returnLabel: 'my proposals',
            },
          });
        },
      },
    ];

    if (CANCELLABLE_STATUSES.includes(proposal.status)) {
      items.push({
        label: 'Cancel proposal',
        icon: 'pi pi-times-circle',
        styleClass: 'row-action--danger',
        command: () => this.openCancelModal(proposal),
      });
    }

    return items;
  }

  protected readonly cancelModalOpen = signal(false);
  protected readonly cancelTarget = signal<ProposalSummary | null>(null);
  protected readonly cancelReason = signal('');
  protected readonly cancelling = signal(false);
  protected readonly cancelError = signal<ApiError | null>(null);

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

  protected openCancelModal(proposal: ProposalSummary): void {
    this.cancelTarget.set(proposal);
    this.cancelReason.set('');
    this.cancelError.set(null);
    this.cancelModalOpen.set(true);
  }

  protected closeCancelModal(): void {
    if (this.cancelling()) return;
    this.cancelModalOpen.set(false);
    this.cancelTarget.set(null);
  }

  protected onCancelReasonInput(event: Event): void {
    this.cancelReason.set((event.target as HTMLTextAreaElement).value);
  }

  protected async confirmCancel(): Promise<void> {
    const target = this.cancelTarget();
    const reason = this.cancelReason().trim();
    if (!target || !reason || this.cancelling()) return;

    this.cancelling.set(true);
    this.cancelError.set(null);

    try {
      await firstValueFrom(this.proposalService.cancelProposal(target.id, { reason }));
      this.cancelModalOpen.set(false);
      this.cancelTarget.set(null);
      this.proposalsResource.reload();
    } catch (err) {
      this.cancelError.set(toApiError(err));
    } finally {
      this.cancelling.set(false);
    }
  }
}
