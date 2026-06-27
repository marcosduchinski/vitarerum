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

import { ApiError, toApiError } from '@core/http/api-error.model';
import { ConfirmModalComponent } from '@shared/components/confirm-modal/confirm-modal.component';
import { ErrorMessageComponent } from '@shared/components/error-message/error-message.component';
import { LoadingStateComponent } from '@shared/components/loading-state/loading-state.component';
import {
  StatusChipComponent,
  WorkflowStatus,
} from '@shared/components/status-chip/status-chip.component';
import { TypeChipComponent } from '@shared/components/type-chip/type-chip.component';

import { ProposalConversationSectionComponent } from '../../components/proposal-conversation-section/proposal-conversation-section.component';
import { ProposalEventsSectionComponent } from '../../components/proposal-events-section/proposal-events-section.component';
import { ProposalOverviewSectionComponent } from '../../components/proposal-overview-section/proposal-overview-section.component';
import { ProposalEvent } from '../../models/proposal.model';
import { PROPOSAL_DETAIL_GROUP_LABELS } from '../../proposal-detail.presentation';
import { PROPOSAL_API_SERVICE } from '../../services/proposal-api.service';

@Component({
  selector: 'app-proposal-others-detail-page',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    RouterLink,
    LoadingStateComponent,
    ErrorMessageComponent,
    ConfirmModalComponent,
    StatusChipComponent,
    TypeChipComponent,
    ProposalOverviewSectionComponent,
    ProposalEventsSectionComponent,
    ProposalConversationSectionComponent,
  ],
  templateUrl: './proposal-others-detail-page.component.html',
  styleUrl: './proposal-others-detail-page.component.scss',
})
export class ProposalOthersDetailPageComponent {
  private readonly proposalService = inject(PROPOSAL_API_SERVICE);
  private readonly router = inject(Router);

  readonly id = input.required<string>();

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

  protected readonly proposal = computed(() => this.proposalResource.value() ?? null);
  protected readonly assignee = computed(() => this.proposal()?.assignedTo ?? null);
  protected readonly messages = computed(() => this.conversationResource.value()?.messages ?? []);
  protected readonly events = computed<readonly ProposalEvent[]>(
    () => this.eventsResource.value()?.content ?? [],
  );
  protected readonly proposalError = computed<ApiError | null>(() => {
    const err = this.proposalResource.error();
    return err ? toApiError(err) : null;
  });

  protected readonly groupLabels = PROPOSAL_DETAIL_GROUP_LABELS;
  protected readonly takingOver = signal(false);
  protected readonly takeOverConfirmOpen = signal(false);
  protected readonly actionError = signal<ApiError | null>(null);

  protected asWorkflowStatus(value: string): WorkflowStatus {
    return value as WorkflowStatus;
  }

  protected requestTakeOverConfirmation(): void {
    if (this.takingOver()) return;
    this.actionError.set(null);
    this.takeOverConfirmOpen.set(true);
  }

  protected cancelTakeOverConfirmation(): void {
    this.takeOverConfirmOpen.set(false);
  }

  protected async takeOver(): Promise<void> {
    if (this.takingOver()) return;

    this.takingOver.set(true);
    this.actionError.set(null);

    try {
      await firstValueFrom(this.proposalService.assignProposal(this.id(), { note: '' }));
      this.takeOverConfirmOpen.set(false);
      // The proposal is now the current user's assignment — take them straight to it.
      void this.router.navigate(['/p/collections/proposals/my-assignments', this.id()]);
    } catch (err) {
      this.actionError.set(toApiError(err));
      this.takeOverConfirmOpen.set(false);
    } finally {
      this.takingOver.set(false);
    }
  }
}
