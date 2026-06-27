import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  input,
  resource,
} from '@angular/core';
import { RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { ApiError, toApiError } from '@core/http/api-error.model';
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
import { PROPOSAL_API_SERVICE } from '../../services/proposal-api.service';

function formatDate(iso: string | undefined): string {
  if (!iso) return '—';
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

@Component({
  selector: 'app-proposal-rejected-detail-page',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    RouterLink,
    LoadingStateComponent,
    ErrorMessageComponent,
    StatusChipComponent,
    TypeChipComponent,
    ProposalOverviewSectionComponent,
    ProposalEventsSectionComponent,
    ProposalConversationSectionComponent,
  ],
  templateUrl: './proposal-rejected-detail-page.component.html',
  styleUrl: './proposal-rejected-detail-page.component.scss',
})
export class ProposalRejectedDetailPageComponent {
  private readonly proposalService = inject(PROPOSAL_API_SERVICE);

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
  protected readonly messages = computed(() => this.conversationResource.value()?.messages ?? []);
  protected readonly events = computed<readonly ProposalEvent[]>(
    () => this.eventsResource.value()?.content ?? [],
  );
  // The rejection entry carries who rejected it, when, and the reason.
  protected readonly rejectionEvent = computed<ProposalEvent | null>(
    () => this.events().find((event) => event.type === 'REJECTED') ?? null,
  );
  protected readonly proposalError = computed<ApiError | null>(() => {
    const err = this.proposalResource.error();
    return err ? toApiError(err) : null;
  });

  protected readonly formatDate = formatDate;

  protected asWorkflowStatus(value: string): WorkflowStatus {
    return value as WorkflowStatus;
  }
}
