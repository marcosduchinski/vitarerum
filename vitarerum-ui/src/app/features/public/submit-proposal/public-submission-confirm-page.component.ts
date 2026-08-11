import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { FeedbackMessageComponent } from '@shared/components/feedback-message/feedback-message.component';
import { LoadingStateComponent } from '@shared/components/loading-state/loading-state.component';

import { PublicI18nPipe } from '../i18n/public-i18n.pipe';
import { PublicI18nService } from '../i18n/public-i18n.service';
import { PublicConfirmationStatus } from '../models/public-proposal.model';
import { PUBLIC_PROPOSAL_API_SERVICE } from '../services/public-proposal-api.service';

type ConfirmState = 'loading' | PublicConfirmationStatus;

interface ConfirmView {
  readonly tone: 'success' | 'warning' | 'danger';
  readonly title: string;
  readonly message: string;
}

/** Tone per outcome; the wording itself comes from the catalogue. */
const TONES: Record<PublicConfirmationStatus, ConfirmView['tone']> = {
  CONFIRMED: 'success',
  ALREADY_CONFIRMED: 'success',
  EXPIRED: 'warning',
  INVALID: 'danger',
};

@Component({
  selector: 'app-public-submission-confirm-page',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FeedbackMessageComponent, LoadingStateComponent, RouterLink, PublicI18nPipe],
  template: `
    <div class="public-result">
      @if (state() === 'loading') {
        <app-loading-state [label]="'public.submitProposal.confirm.loading' | t" />
      } @else {
        <app-feedback-message
          [tone]="view().tone"
          [title]="view().title"
          [message]="view().message"
        />
        @if (state() !== 'CONFIRMED' && state() !== 'ALREADY_CONFIRMED') {
          <p class="public-result__note">
            <a routerLink="/submit-proposal">{{
              'public.submitProposal.confirm.startNew' | t
            }}</a>
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
  private readonly i18n = inject(PublicI18nService);

  protected readonly state = signal<ConfirmState>('loading');
  protected readonly reference = signal<string | undefined>(undefined);

  protected readonly view = computed<ConfirmView>(() => {
    const status = this.state() as PublicConfirmationStatus;
    return {
      tone: TONES[status],
      title: this.i18n.t(`public.submitProposal.confirm.${status}.title`),
      message: this.i18n.t(`public.submitProposal.confirm.${status}.message`),
    };
  });

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
