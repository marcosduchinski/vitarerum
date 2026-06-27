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
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { groupNameOf } from '@core/auth/models/permission.model';
import { ApiError, toApiError } from '@core/http/api-error.model';
import { USER_MANAGEMENT_SERVICE } from '@features/admin/services/user-management.service';
import { ConfirmModalComponent } from '@shared/components/confirm-modal/confirm-modal.component';
import { ErrorMessageComponent } from '@shared/components/error-message/error-message.component';
import { FeedbackMessageComponent } from '@shared/components/feedback-message/feedback-message.component';
import { LoadingStateComponent } from '@shared/components/loading-state/loading-state.component';
import { ProposalChatPanelComponent } from '@features/proposal-chat/components/proposal-chat-panel/proposal-chat-panel.component';
import {
  StatusChipComponent,
  WorkflowStatus,
} from '@shared/components/status-chip/status-chip.component';
import { TypeChipComponent } from '@shared/components/type-chip/type-chip.component';

import { PROPOSAL_API_SERVICE } from '../../services/proposal-api.service';
import {
  ProposalConversationSectionComponent,
  ReplyComposerPayload,
} from '../../components/proposal-conversation-section/proposal-conversation-section.component';
import { ProposalEventsSectionComponent } from '../../components/proposal-events-section/proposal-events-section.component';
import { ProposalOverviewSectionComponent } from '../../components/proposal-overview-section/proposal-overview-section.component';
import { PROPOSAL_DETAIL_GROUP_LABELS, StaffOption } from '../../proposal-detail.presentation';
import { Message } from '../../models/proposal.model';

type MyDetailPanel = 'overview' | 'conversation' | 'ai-assistance' | 'actions';

@Component({
  selector: 'app-proposal-my-detail-page',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    RouterLink,
    LoadingStateComponent,
    ErrorMessageComponent,
    FeedbackMessageComponent,
    StatusChipComponent,
    TypeChipComponent,
    ConfirmModalComponent,
    ProposalOverviewSectionComponent,
    ProposalConversationSectionComponent,
    ProposalEventsSectionComponent,
    ProposalChatPanelComponent,
  ],
  templateUrl: './proposal-my-detail-page.component.html',
  styleUrl: './proposal-my-detail-page.component.scss',
})
export class ProposalMyDetailPageComponent {
  private readonly proposalService = inject(PROPOSAL_API_SERVICE);
  private readonly userService = inject(USER_MANAGEMENT_SERVICE);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);

  readonly id = input.required<string>();

  // The active tab and the message under triage live in the URL (query params,
  // bound via withComponentInputBinding) so the view is shareable and survives a
  // refresh. linkedSignal keeps them locally writable while resetting to the URL
  // whenever the params change.
  readonly tab = input<string>();
  readonly triageMessageId = input<string>();

  protected readonly proposalResource = resource({
    params: () => this.id(),
    loader: ({ params }) => firstValueFrom(this.proposalService.getProposal(params)),
  });

  protected readonly conversationResource = resource({
    params: () => this.id(),
    loader: ({ params }) => firstValueFrom(this.proposalService.getConversation(params)),
  });

  protected readonly eventsResource = resource({
    params: () => this.id(),
    loader: ({ params }) => firstValueFrom(this.proposalService.listEvents(params)),
  });

  protected readonly staffUsersResource = resource({
    loader: () => firstValueFrom(this.userService.listUsers({ size: 100 })),
  });

  protected readonly proposal = computed(() => this.proposalResource.value() ?? null);
  protected readonly messages = computed(() => this.conversationResource.value()?.messages ?? []);
  protected readonly events = computed(() => this.eventsResource.value()?.content ?? []);
  protected readonly staffOptions = computed<StaffOption[]>(() =>
    (this.staffUsersResource.value()?.content ?? []).flatMap((u) =>
      u.permissions.flatMap((p) => {
        const groupName = groupNameOf(p.group);
        if (groupName === 'EXTERNAL') return [];
        return [
          {
            label: `${u.name} - ${PROPOSAL_DETAIL_GROUP_LABELS[groupName]}`,
            permissionId: p.permissionId,
          },
        ];
      }),
    ),
  );
  protected readonly proposalError = computed<ApiError | null>(() => {
    const err = this.proposalResource.error();
    return err ? toApiError(err) : null;
  });

  protected readonly activePanel = linkedSignal<MyDetailPanel>(() => this.normalizeTab(this.tab()));
  protected readonly accepting = signal(false);
  protected readonly rejecting = signal(false);
  protected readonly forwarding = signal(false);
  protected readonly acceptConfirmOpen = signal(false);
  protected readonly rejectModalOpen = signal(false);
  protected readonly forwardModalOpen = signal(false);
  protected readonly rejectionReason = signal('');
  protected readonly forwardTargetPermissionId = signal('');
  protected readonly forwardNote = signal('');
  protected readonly replyResetVersion = signal(0);
  protected readonly sendingMessage = signal(false);
  protected readonly actionError = signal<ApiError | null>(null);
  protected readonly messageError = signal<ApiError | null>(null);
  protected readonly temporaryExternalUserEmail = linkedSignal<string | null>(() => {
    this.id();
    return null;
  });
  protected readonly selectedTriageMessageId = linkedSignal<string | null>(
    () => this.triageMessageId() ?? null,
  );

  protected readonly canDecide = computed(() => this.proposal()?.status === 'PENDING');
  protected readonly canEdit = computed(() => {
    const status = this.proposal()?.status;
    return status === 'SUBMITTED' || status === 'PENDING';
  });

  // Negative terminal outcome — drawn as a red off-shoot on the lifecycle rail,
  // mirroring the cancelled step on the project detail page.
  protected readonly closedOutcome = computed<string | null>(() => {
    switch (this.proposal()?.status) {
      case 'REJECTED':
        return 'Rejected';
      case 'CANCELLED':
        return 'Cancelled';
      default:
        return null;
    }
  });

  // Lifecycle rail for the Actions panel: Submitted -> Under review -> Decided.
  // A negative outcome leaves every forward step un-reached (see closedOutcome).
  protected readonly lifecycle = computed(() => {
    const status = this.proposal()?.status ?? 'SUBMITTED';
    const steps = [
      { key: 'SUBMITTED', label: 'Submitted' },
      { key: 'PENDING', label: 'Under review' },
      { key: 'APPROVED', label: 'Decided' },
    ] as const;
    const reachedIndex: Record<string, number> = { SUBMITTED: 0, PENDING: 1, APPROVED: 2 };
    const currentIndex = this.closedOutcome() ? -1 : (reachedIndex[status] ?? 0);
    return steps.map((step, index) => ({
      label: step.label,
      done: currentIndex > index,
      current: currentIndex === index,
    }));
  });
  protected readonly forwardTargetLabel = computed(
    () =>
      this.staffOptions().find((o) => o.permissionId === this.forwardTargetPermissionId())?.label ??
      'the selected staff member',
  );

  protected asWorkflowStatus(value: string): WorkflowStatus {
    return value as WorkflowStatus;
  }

  protected edit(): void {
    void this.router.navigate(['/p/collections/proposals/my-assignments', this.id(), 'edit']);
  }

  protected createTemporaryExternalUser(): void {
    const email = this.proposal()?.requestedBy.user.email;
    if (email && !this.temporaryExternalUserEmail()) {
      this.temporaryExternalUserEmail.set(email);
    }
  }

  protected selectPanel(panel: MyDetailPanel): void {
    this.activePanel.set(panel);
    this.syncUrl({ tab: panel });
  }

  protected openTriage(message: Message): void {
    this.selectedTriageMessageId.set(message.id);
    this.activePanel.set('ai-assistance');
    this.syncUrl({ tab: 'ai-assistance', triageMessageId: message.id });
  }

  protected onTriageApplied(): void {
    this.proposalResource.reload();
    this.eventsResource.reload();
    this.selectedTriageMessageId.set(null);
    this.activePanel.set('overview');
    this.syncUrl({ tab: 'overview', triageMessageId: null });
  }

  protected onRequestedObjectsAdded(): void {
    this.proposalResource.reload();
  }

  private normalizeTab(tab: string | undefined): MyDetailPanel {
    return tab === 'conversation' || tab === 'ai-assistance' || tab === 'actions'
      ? tab
      : 'overview';
  }

  /** Reflects the current view state into the URL query string. A null value drops
   *  the param (the 'overview' tab is the default, so its URL stays clean). */
  private syncUrl(state: { tab?: MyDetailPanel; triageMessageId?: string | null }): void {
    const queryParams: Record<string, string | null> = {};
    if (state.tab !== undefined) {
      queryParams['tab'] = state.tab === 'overview' ? null : state.tab;
    }
    if (state.triageMessageId !== undefined) {
      queryParams['triageMessageId'] = state.triageMessageId;
    }
    void this.router
      .navigate([], {
        relativeTo: this.route,
        queryParams,
        queryParamsHandling: 'merge',
        replaceUrl: true,
      })
      .catch(() => undefined);
  }

  protected openRejectModal(): void {
    this.rejectionReason.set('');
    this.acceptConfirmOpen.set(false);
    this.actionError.set(null);
    this.rejectModalOpen.set(true);
  }

  protected closeRejectModal(): void {
    this.rejectModalOpen.set(false);
  }

  protected onRejectionReasonInput(event: Event): void {
    this.rejectionReason.set((event.target as HTMLTextAreaElement).value);
  }

  protected openForwardModal(): void {
    this.forwardTargetPermissionId.set('');
    this.forwardNote.set('');
    this.actionError.set(null);
    this.forwardModalOpen.set(true);
  }

  protected closeForwardModal(): void {
    this.forwardModalOpen.set(false);
  }

  protected onForwardTargetChange(event: Event): void {
    this.forwardTargetPermissionId.set((event.target as HTMLSelectElement).value);
  }

  protected onForwardNoteChange(event: Event): void {
    this.forwardNote.set((event.target as HTMLTextAreaElement).value);
  }

  protected async forward(): Promise<void> {
    const targetPermissionId = this.forwardTargetPermissionId();
    if (!targetPermissionId || this.forwarding()) return;

    this.forwarding.set(true);
    this.actionError.set(null);

    try {
      await firstValueFrom(
        this.proposalService.forwardProposal(this.id(), {
          targetPermissionId,
          note: this.forwardNote(),
        }),
      );
      this.forwardModalOpen.set(false);
      this.proposalResource.reload();
      this.eventsResource.reload();
    } catch (err) {
      this.actionError.set(toApiError(err));
    } finally {
      this.forwarding.set(false);
    }
  }

  protected async sendReply(payload: ReplyComposerPayload): Promise<void> {
    if (this.sendingMessage()) return;

    this.sendingMessage.set(true);
    this.messageError.set(null);

    try {
      const uploadedDocuments = [];
      for (const file of payload.files) {
        uploadedDocuments.push(
          await firstValueFrom(
            this.proposalService.uploadDocument(this.id(), file, 'STAFF_RESPONSE_ATTACHMENT'),
          ),
        );
      }

      await firstValueFrom(
        this.proposalService.sendMessage(this.id(), {
          recipient: this.proposal()?.requestedBy.user.email ?? '',
          subject: `Response to ${this.proposal()?.referenceNumber ?? 'proposal'}`,
          body: payload.body,
          documentIds: uploadedDocuments.map((document) => document.id),
        }),
      );

      this.replyResetVersion.update((version) => version + 1);
      this.proposalResource.reload();
      this.conversationResource.reload();
      this.eventsResource.reload();
    } catch (err) {
      this.messageError.set(toApiError(err));
    } finally {
      this.sendingMessage.set(false);
    }
  }

  protected requestAcceptConfirmation(): void {
    if (this.accepting() || this.rejecting()) return;
    this.actionError.set(null);
    this.acceptConfirmOpen.set(true);
  }

  protected cancelAcceptConfirmation(): void {
    this.acceptConfirmOpen.set(false);
  }

  protected async accept(): Promise<void> {
    if (this.accepting() || this.rejecting()) return;
    const proposal = this.proposal();
    if (!proposal) return;

    this.accepting.set(true);
    this.actionError.set(null);

    try {
      await firstValueFrom(
        // The project is materialised from the proposal: its title becomes both the
        // project title and purpose, and the requested period becomes its dates.
        this.proposalService.approveProposal(this.id(), {
          title: proposal.collectionUseProject?.title ?? '',
          purpose: proposal.title,
          beginDate: proposal.beginDate ?? '',
          endDate: proposal.endDate ?? '',
          note: 'Accepted from my assignment detail.',
        }),
      );
      await this.router.navigate(['/p/collections/proposals/approved']);
    } catch (err) {
      this.actionError.set(toApiError(err));
      this.acceptConfirmOpen.set(false);
    } finally {
      this.accepting.set(false);
    }
  }

  protected async reject(): Promise<void> {
    const reason = this.rejectionReason().trim();
    if (!reason || this.rejecting() || this.accepting()) return;

    this.rejecting.set(true);
    this.actionError.set(null);

    try {
      await firstValueFrom(this.proposalService.rejectProposal(this.id(), { reason }));
      await this.router.navigate(['/p/collections/proposals/rejected']);
    } catch (err) {
      this.actionError.set(toApiError(err));
      this.rejectModalOpen.set(false);
    } finally {
      this.rejecting.set(false);
    }
  }
}
