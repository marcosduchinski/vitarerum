import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { FeedbackMessageComponent } from '@shared/components/feedback-message/feedback-message.component';
import { LoadingStateComponent } from '@shared/components/loading-state/loading-state.component';

import { PublicConfirmationStatus } from '../models/public-proposal.model';
import { PUBLIC_PROPOSAL_API_SERVICE } from '../services/public-proposal-api.service';

type ConfirmState = 'loading' | PublicConfirmationStatus;

interface ConfirmView {
  readonly tone: 'success' | 'warning' | 'danger';
  readonly title: string;
  readonly message: string;
}

@Component({
  selector: 'app-public-submission-confirm-page',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FeedbackMessageComponent, LoadingStateComponent, RouterLink],
  template: `
    <div class="public-result">
      @if (state() === 'loading') {
        <app-loading-state label="Confirming your request…" />
      } @else {
        <app-feedback-message [tone]="view().tone" [title]="view().title" [message]="view().message" />
        @if (state() !== 'CONFIRMED' && state() !== 'ALREADY_CONFIRMED') {
          <p class="public-result__note">
            <a routerLink="/submit-proposal">Start a new request</a>
          </p>
        }
      }
    </div>
  `,
  styles: `
    .public-result {
      display: grid;
      gap: 1rem;
    }
    .public-result__note {
      margin: 0;
      font-size: 0.9rem;
    }
  `,
})
export class PublicSubmissionConfirmPageComponent {
  private readonly publicProposals = inject(PUBLIC_PROPOSAL_API_SERVICE);
  private readonly route = inject(ActivatedRoute);

  protected readonly state = signal<ConfirmState>('loading');
  protected readonly reference = signal<string | undefined>(undefined);

  protected readonly view = computed<ConfirmView>(() => VIEWS[this.state() as PublicConfirmationStatus]);

  constructor() {
    void this.confirm();
  }

  private async confirm(): Promise<void> {
    const token = this.route.snapshot.queryParamMap.get('token') ?? '';
    if (!token) {
      this.state.set('INVALID');
      return;
    }
    try {
      const result = await firstValueFrom(this.publicProposals.confirm(token));
      this.reference.set(result.referenceNumber);
      this.state.set(result.status);
    } catch {
      this.state.set('INVALID');
    }
  }
}

const VIEWS: Record<PublicConfirmationStatus, ConfirmView> = {
  CONFIRMED: {
    tone: 'success',
    title: 'Request confirmed',
    message:
      'Thank you — your proposal has been forwarded to the collections team. They will reply to your e-mail.',
  },
  ALREADY_CONFIRMED: {
    tone: 'success',
    title: 'Already confirmed',
    message: 'This request was already confirmed. The collections team has it — no further action needed.',
  },
  EXPIRED: {
    tone: 'warning',
    title: 'Link expired',
    message: 'This confirmation link has expired. Please submit your request again to receive a fresh link.',
  },
  INVALID: {
    tone: 'danger',
    title: 'Invalid link',
    message: 'We couldn’t confirm this request. The link may be incomplete. Please submit your request again.',
  },
};
