import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  input,
  linkedSignal,
  resource,
  signal,
} from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { IDENTITY_SERVICE } from '@core/auth/identity.service';
import { groupNameOf } from '@core/auth/models/permission.model';
import { ApiError, toApiError } from '@core/http/api-error.model';
import { USER_MANAGEMENT_SERVICE } from '@features/admin/services/user-management.service';
import { ConfirmModalComponent } from '@shared/components/confirm-modal/confirm-modal.component';
import { ErrorMessageComponent } from '@shared/components/error-message/error-message.component';
import { LoadingStateComponent } from '@shared/components/loading-state/loading-state.component';
import {
  StatusChipComponent,
  WorkflowStatus,
} from '@shared/components/status-chip/status-chip.component';
import { TypeChipComponent } from '@shared/components/type-chip/type-chip.component';

import { ProposalDocumentsSectionComponent } from '../../components/proposal-documents-section/proposal-documents-section.component';
import { ProposalEventsSectionComponent } from '../../components/proposal-events-section/proposal-events-section.component';
import { ProposalObjectsSectionComponent } from '../../components/proposal-objects-section/proposal-objects-section.component';
import { ProposalOverviewSectionComponent } from '../../components/proposal-overview-section/proposal-overview-section.component';
import { StaffOption } from '../../proposal-detail.presentation';
import { PROPOSAL_API_SERVICE } from '../../services/proposal-api.service';

type DirectionPanel = 'overview' | 'events' | 'documents' | 'objects' | 'actions';

@Component({
  selector: 'app-proposal-direction-detail-page',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    RouterLink,
    LoadingStateComponent,
    ErrorMessageComponent,
    StatusChipComponent,
    TypeChipComponent,
    ConfirmModalComponent,
    ProposalOverviewSectionComponent,
    ProposalEventsSectionComponent,
    ProposalDocumentsSectionComponent,
    ProposalObjectsSectionComponent,
  ],
  templateUrl: './proposal-direction-detail-page.component.html',
  styleUrl: './proposal-direction-detail-page.component.scss',
})
export class ProposalDirectionDetailPageComponent {
  private readonly proposalService = inject(PROPOSAL_API_SERVICE);
  private readonly users = inject(USER_MANAGEMENT_SERVICE);
  private readonly identity = inject(IDENTITY_SERVICE);
  private readonly router = inject(Router);

  readonly id = input.required<string>();
  readonly tab = input<string>();

  protected readonly tabs: readonly { id: DirectionPanel; label: string }[] = [
    { id: 'overview', label: 'Overview' },
    { id: 'events', label: 'Event Log' },
    { id: 'documents', label: 'Documents' },
    { id: 'objects', label: 'Objects' },
    { id: 'actions', label: 'Actions' },
  ];

  protected readonly proposalResource = resource({
    params: () => this.id(),
    loader: ({ params }) => firstValueFrom(this.proposalService.getProposal(params)),
  });
  protected readonly eventsResource = resource({
    params: () => this.id(),
    loader: ({ params }) => firstValueFrom(this.proposalService.listEvents(params)),
  });
  protected readonly usersResource = resource({
    loader: () => firstValueFrom(this.users.listUsers({ size: 100 })),
  });

  protected readonly proposal = computed(() => this.proposalResource.value() ?? null);
  protected readonly events = computed(() => this.eventsResource.value()?.content ?? []);
  protected readonly error = computed<ApiError | null>(() => {
    const value = this.proposalResource.error();
    return value ? toApiError(value) : null;
  });
  protected readonly isCurrentAssignment = computed(
    () => this.proposal()?.assignedTo?.permissionId === this.identity.getPermissionId(),
  );
  protected readonly staffOptions = computed<StaffOption[]>(() =>
    (this.usersResource.value()?.content ?? []).flatMap((user) => {
      if (user.status === 'DISABLED') return [];
      return user.permissions.flatMap((permission) => {
        const group = groupNameOf(permission.group);
        return group === 'CURATORIAL' || group === 'COLLECTIONS_MANAGEMENT'
          ? [
              {
                label: `${user.name} - ${group.replaceAll('_', ' ')}`,
                permissionId: permission.permissionId,
              },
            ]
          : [];
      });
    }),
  );

  protected readonly activePanel = linkedSignal<DirectionPanel>(() =>
    this.normalizeTab(this.tab()),
  );
  protected readonly returnModalOpen = signal(false);
  protected readonly targetPermissionId = signal('');
  protected readonly reason = signal('');
  protected readonly returning = signal(false);
  protected readonly actionError = signal<ApiError | null>(null);

  protected asWorkflowStatus(value: string): WorkflowStatus {
    return value as WorkflowStatus;
  }

  protected selectPanel(panel: DirectionPanel): void {
    this.activePanel.set(panel);
    void this.router.navigate([], {
      queryParams: { tab: panel === 'overview' ? null : panel },
      queryParamsHandling: 'merge',
      replaceUrl: true,
    });
  }

  protected onTabKeydown(event: KeyboardEvent, index: number): void {
    let nextIndex: number | null = null;
    if (event.key === 'ArrowRight') nextIndex = (index + 1) % this.tabs.length;
    if (event.key === 'ArrowLeft') nextIndex = (index - 1 + this.tabs.length) % this.tabs.length;
    if (event.key === 'Home') nextIndex = 0;
    if (event.key === 'End') nextIndex = this.tabs.length - 1;
    if (nextIndex === null) return;

    event.preventDefault();
    this.selectPanel(this.tabs[nextIndex].id);
    const tabElements = (event.currentTarget as HTMLElement)
      .closest('[role="tablist"]')
      ?.querySelectorAll<HTMLButtonElement>('[role="tab"]');
    queueMicrotask(() => tabElements?.item(nextIndex)?.focus());
  }

  protected openReturnModal(): void {
    this.targetPermissionId.set('');
    this.reason.set('');
    this.actionError.set(null);
    this.returnModalOpen.set(true);
  }

  protected closeReturnModal(): void {
    this.returnModalOpen.set(false);
  }

  protected onTargetChange(event: Event): void {
    this.targetPermissionId.set((event.target as HTMLSelectElement).value);
  }

  protected onReasonInput(event: Event): void {
    this.reason.set((event.target as HTMLTextAreaElement).value);
  }

  protected async returnToStaff(): Promise<void> {
    const targetPermissionId = this.targetPermissionId();
    const reason = this.reason().trim();
    if (!targetPermissionId || !reason || this.returning()) return;
    this.returning.set(true);
    this.actionError.set(null);
    try {
      await firstValueFrom(
        this.proposalService.returnProposalToStaff(this.id(), { targetPermissionId, reason }),
      );
      this.returnModalOpen.set(false);
      await this.router.navigate(['/p/collections/proposals/my-assignments']);
    } catch (err) {
      this.actionError.set(toApiError(err));
    } finally {
      this.returning.set(false);
    }
  }

  private normalizeTab(tab: string | undefined): DirectionPanel {
    return tab === 'events' || tab === 'documents' || tab === 'objects' || tab === 'actions'
      ? tab
      : 'overview';
  }
}
