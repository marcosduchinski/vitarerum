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

import { IDENTITY_SERVICE } from '@core/auth/identity.service';
import { GroupName } from '@core/auth/models/group-name.enum';
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

import {
  ProposalConversationSectionComponent,
  ReplyComposerPayload,
} from '../../components/proposal-conversation-section/proposal-conversation-section.component';

interface ForwardStaffOption {
  readonly label: string;
  readonly permissionId: string;
}
import { PROPOSAL_API_SERVICE } from '../../services/proposal-api.service';

const GROUP_LABELS: Record<GroupName, string> = {
  EXTERNAL: 'External',
  COLLECTIONS_MANAGEMENT: 'Collections management',
  CURATORIAL: 'Curatorial',
  DIRECTION: 'Direction',
  SYS_ADMIN: 'Administration',
};

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString('en-GB', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
    });
  } catch {
    return iso;
  }
}

function formatDateTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString('en-GB', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

function safeReturnTo(value: string | undefined): string {
  return value?.startsWith('/p/collections/proposals') ? value : '/p/collections/proposals/new';
}

function safeReturnLabel(value: string | undefined): string {
  const trimmed = value?.trim();
  return trimmed ? trimmed : 'new proposals';
}

@Component({
  selector: 'app-proposal-detail-page',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    RouterLink,
    LoadingStateComponent,
    ErrorMessageComponent,
    StatusChipComponent,
    TypeChipComponent,
    ConfirmModalComponent,
    ProposalConversationSectionComponent,
  ],
  templateUrl: './proposal-detail-page.component.html',
  styleUrl: './proposal-detail-page.component.scss',
})
export class ProposalDetailPageComponent {
  private readonly proposalService = inject(PROPOSAL_API_SERVICE);
  private readonly userService = inject(USER_MANAGEMENT_SERVICE);
  private readonly identity = inject(IDENTITY_SERVICE);
  private readonly router = inject(Router);

  readonly id = input.required<string>();
  readonly returnTo = input<string>();
  readonly returnLabel = input<string>();

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
  protected readonly backLink = computed(() => safeReturnTo(this.returnTo()));
  protected readonly backLabel = computed(() => `Back to ${safeReturnLabel(this.returnLabel())}`);
  protected readonly messages = computed(() => this.conversationResource.value()?.messages ?? []);
  protected readonly events = computed(() => this.eventsResource.value()?.content ?? []);
  // Routing actions (assume/forward) are staff-only. This shared detail page is
  // reachable by external researchers via their own proposals, so gate on isStaff
  // in addition to the proposal being in an assignable state.
  protected readonly canAssign = computed(() => {
    const proposal = this.proposal();
    return (
      this.identity.isStaff() && proposal?.status === 'SUBMITTED' && proposal.assignedTo === null
    );
  });
  protected readonly staffOptions = computed<ForwardStaffOption[]>(() =>
    (this.staffUsersResource.value()?.content ?? []).flatMap((u) =>
      u.permissions.flatMap((p) => {
        const groupName = groupNameOf(p.group);
        if (groupName === 'EXTERNAL') return [];
        return [{ label: `${u.name} — ${GROUP_LABELS[groupName]}`, permissionId: p.permissionId }];
      }),
    ),
  );

  protected readonly proposalError = computed(() => {
    const err = this.proposalResource.error();
    return err ? toApiError(err) : null;
  });

  protected readonly formatDate = formatDate;
  protected readonly formatDateTime = formatDateTime;
  protected readonly assuming = signal(false);
  protected readonly assumeConfirmOpen = signal(false);
  protected readonly forwarding = signal(false);
  protected readonly forwardModalOpen = signal(false);
  protected readonly forwardTargetPermissionId = signal('');
  protected readonly forwardTargetLabel = computed(
    () =>
      this.staffOptions().find((option) => option.permissionId === this.forwardTargetPermissionId())
        ?.label ?? 'the selected staff member',
  );
  protected readonly forwardNote = signal('');
  protected readonly actionError = signal<ApiError | null>(null);
  protected readonly sendingMessage = signal(false);
  protected readonly messageError = signal<ApiError | null>(null);
  protected readonly replyResetVersion = signal(0);
  protected readonly staffRecipientEmail = computed<string | null>(() => {
    const assignedTo = this.proposal()?.assignedTo;
    return assignedTo ? assignedTo.user.email : null;
  });

  protected asWorkflowStatus(value: string): WorkflowStatus {
    return value as WorkflowStatus;
  }

  protected async sendReply(payload: ReplyComposerPayload): Promise<void> {
    const recipientEmail = this.proposal()?.assignedTo?.user.email;
    if (!recipientEmail || this.sendingMessage()) return;

    this.sendingMessage.set(true);
    this.messageError.set(null);

    try {
      const uploadedDocuments = [];
      for (const file of payload.files) {
        uploadedDocuments.push(
          await firstValueFrom(
            this.proposalService.uploadDocument(this.id(), file, 'REQUESTER_ATTACHMENT'),
          ),
        );
      }

      await firstValueFrom(
        this.proposalService.sendMessage(this.id(), {
          recipient: recipientEmail,
          subject: `Response to ${this.proposal()?.referenceNumber ?? 'proposal'}`,
          body: payload.body,
          documentIds: uploadedDocuments.map((d) => d.id),
        }),
      );

      this.replyResetVersion.update((v) => v + 1);
      this.reloadWorkflow();
      this.conversationResource.reload();
    } catch (err) {
      this.messageError.set(toApiError(err));
    } finally {
      this.sendingMessage.set(false);
    }
  }

  protected requestAssumeConfirmation(): void {
    if (!this.canAssign() || this.assuming()) return;
    this.assumeConfirmOpen.set(true);
  }

  protected cancelAssumeConfirmation(): void {
    this.assumeConfirmOpen.set(false);
  }

  protected async assume(): Promise<void> {
    if (!this.canAssign() || this.assuming()) return;

    this.assuming.set(true);
    this.actionError.set(null);

    try {
      await firstValueFrom(
        this.proposalService.assignProposal(this.id(), {
          note: 'Assigned to self from proposal detail.',
        }),
      );
      this.assumeConfirmOpen.set(false);
      // The proposal is now the current user's assignment — take them straight to it.
      void this.router.navigate(['/p/collections/proposals/my-assignments', this.id()]);
    } catch (err) {
      this.actionError.set(toApiError(err));
      this.assumeConfirmOpen.set(false);
    } finally {
      this.assuming.set(false);
    }
  }

  protected openForwardModal(): void {
    this.forwardModalOpen.set(true);
    this.forwardTargetPermissionId.set('');
    this.forwardNote.set('');
    this.actionError.set(null);
  }

  protected closeForwardModal(): void {
    this.forwardModalOpen.set(false);
    this.forwardTargetPermissionId.set('');
    this.forwardNote.set('');
  }

  protected onForwardTargetChange(event: Event): void {
    this.forwardTargetPermissionId.set((event.target as HTMLSelectElement).value);
  }

  protected onForwardNoteChange(event: Event): void {
    this.forwardNote.set((event.target as HTMLTextAreaElement).value);
  }

  protected async forward(): Promise<void> {
    const targetPermissionId = this.forwardTargetPermissionId();
    if (!this.canAssign() || !targetPermissionId || this.forwarding()) return;

    this.forwarding.set(true);
    this.actionError.set(null);

    try {
      await firstValueFrom(
        this.proposalService.forwardProposal(this.id(), {
          targetPermissionId,
          note: this.forwardNote(),
        }),
      );
      this.closeForwardModal();
      this.reloadWorkflow();
    } catch (err) {
      this.actionError.set(toApiError(err));
    } finally {
      this.forwarding.set(false);
    }
  }

  private reloadWorkflow(): void {
    this.proposalResource.reload();
    this.eventsResource.reload();
  }
}
