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
import { GroupName } from '@core/auth/models/group-name.enum';
import { groupNameOf } from '@core/auth/models/permission.model';
import { ApiError, toApiError } from '@core/http/api-error.model';
import { USER_MANAGEMENT_SERVICE } from '@features/admin/services/user-management.service';
import { ConfirmModalComponent } from '@shared/components/confirm-modal/confirm-modal.component';
import { EmptyStateComponent } from '@shared/components/empty-state/empty-state.component';
import { ErrorMessageComponent } from '@shared/components/error-message/error-message.component';
import { FeedbackMessageComponent } from '@shared/components/feedback-message/feedback-message.component';
import { LoadingStateComponent } from '@shared/components/loading-state/loading-state.component';
import { PageHeaderComponent } from '@shared/components/page-header/page-header.component';
import { RowActionsComponent } from '@shared/components/row-actions/row-actions.component';
import { TypeChipComponent } from '@shared/components/type-chip/type-chip.component';
import { Page } from '@shared/models/page.model';

import { ProposalSummary } from '../../models/proposal.model';
import { PROPOSAL_API_SERVICE } from '../../services/proposal-api.service';

interface ForwardStaffOption {
  readonly label: string;
  readonly permissionId: string;
}

const DEFAULT_PAGE_SIZE = 20;
const PAGE_SIZE_OPTIONS = [10, 20, 50, 100] as const;

const GROUP_LABELS: Record<GroupName, string> = {
  EXTERNAL: 'External',
  COLLECTIONS_MANAGEMENT: 'Collections management',
  CURATORIAL: 'Curatorial',
  DIRECTION: 'Direction',
  SYS_ADMIN: 'Administration',
};

function emptyProposalPage(page: number, size: number): Page<ProposalSummary> {
  return { content: [], page, size, totalElements: 0, totalPages: 0 };
}

@Component({
  selector: 'app-proposals-my-assignments-page',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    RouterLink,
    RowActionsComponent,
    PageHeaderComponent,
    LoadingStateComponent,
    ErrorMessageComponent,
    FeedbackMessageComponent,
    EmptyStateComponent,
    ConfirmModalComponent,
    TypeChipComponent,
  ],
  templateUrl: './proposals-my-assignments-page.component.html',
  styleUrl: './proposals-my-assignments-page.component.scss',
})
export class ProposalsMyAssignmentsPageComponent {
  private readonly identity = inject(IDENTITY_SERVICE);
  private readonly proposalService = inject(PROPOSAL_API_SERVICE);
  private readonly userService = inject(USER_MANAGEMENT_SERVICE);
  private readonly router = inject(Router);

  protected readonly currentPage = signal(0);
  protected readonly pageSize = signal(DEFAULT_PAGE_SIZE);
  protected readonly searchDraft = signal('');
  protected readonly appliedSearch = signal('');

  // Staff directory for the forward picker only. The assignments list no longer
  // depends on this (see currentPermissionId), so a failure here degrades the
  // picker without blanking the list.
  protected readonly usersResource = resource({
    loader: () => firstValueFrom(this.userService.listUsers({ size: 100 })),
  });

  // The active permission id comes straight from the session — no need to fetch
  // the (admin-only) user directory to look it up.
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
          assignedTo: params.currentPermissionId,
          status: 'PENDING',
          page: params.page,
          size: params.size,
          search: params.search,
        }),
      );
    },
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
  protected readonly staffOptions = computed<ForwardStaffOption[]>(() =>
    (this.usersResource.value()?.content ?? []).flatMap((user) =>
      user.permissions.flatMap((permission) => {
        const groupName = groupNameOf(permission.group);
        if (groupName === 'EXTERNAL') return [];
        return [
          { label: `${user.name} — ${GROUP_LABELS[groupName]}`, permissionId: permission.permissionId },
        ];
      }),
    ),
  );

  protected actionItemsFor(proposal: ProposalSummary): MenuItem[] {
    const proposalId = proposal.id;

    return [
      {
        label: 'Forward',
        icon: 'pi pi-send',
        command: () => this.openForwardModal(proposalId),
      },
      {
        label: 'Details',
        icon: 'pi pi-eye',
        command: () => {
          void this.router.navigate(['/p/collections/proposals/my-assignments', proposalId]);
        },
      },
    ];
  }

  protected readonly forwardModalProposalId = signal<string | null>(null);
  protected readonly forwardModalProposal = computed(() => {
    const proposalId = this.forwardModalProposalId();
    return this.proposals().find((proposal) => proposal.id === proposalId) ?? null;
  });
  protected readonly forwardTargetPermissionId = signal('');
  protected readonly forwardTargetLabel = computed(
    () =>
      this.staffOptions().find((option) => option.permissionId === this.forwardTargetPermissionId())
        ?.label ?? 'the selected staff member',
  );
  protected readonly forwardNote = signal('');
  protected readonly forwardPending = signal(false);
  protected readonly forwardError = signal<ApiError | null>(null);
  protected readonly forwardSuccessMessage = signal<string | null>(null);

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

  protected openForwardModal(proposalId: string): void {
    this.forwardModalProposalId.set(proposalId);
    this.forwardTargetPermissionId.set('');
    this.forwardNote.set('');
    this.forwardError.set(null);
  }

  protected closeForwardModal(): void {
    this.forwardModalProposalId.set(null);
  }

  protected onForwardTargetChange(event: Event): void {
    this.forwardTargetPermissionId.set((event.target as HTMLSelectElement).value);
  }

  protected onForwardNoteChange(event: Event): void {
    this.forwardNote.set((event.target as HTMLTextAreaElement).value);
  }

  protected dismissForwardSuccess(): void {
    this.forwardSuccessMessage.set(null);
  }

  protected async forward(proposalId: string): Promise<void> {
    const targetPermissionId = this.forwardTargetPermissionId();
    if (!targetPermissionId || this.forwardPending()) return;
    const proposalReference =
      this.forwardModalProposal()?.referenceNumber ?? 'The proposal';

    this.forwardPending.set(true);
    this.forwardError.set(null);

    try {
      await firstValueFrom(
        this.proposalService.forwardProposal(proposalId, {
          targetPermissionId,
          note: this.forwardNote(),
        }),
      );
      this.forwardModalProposalId.set(null);
      this.forwardSuccessMessage.set(
        `${proposalReference} was forwarded to ${this.forwardTargetLabel()}.`,
      );
      this.proposalsResource.reload();
    } catch (err) {
      this.forwardError.set(toApiError(err));
    } finally {
      this.forwardPending.set(false);
    }
  }
}
