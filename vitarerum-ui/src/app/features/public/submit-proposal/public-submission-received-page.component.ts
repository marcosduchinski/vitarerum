import { ChangeDetectionStrategy, Component, inject, input } from '@angular/core';
import { RouterLink } from '@angular/router';

import { FeedbackMessageComponent } from '@shared/components/feedback-message/feedback-message.component';

import { PublicI18nPipe } from '../i18n/public-i18n.pipe';
import { PublicI18nService } from '../i18n/public-i18n.service';

/**
 * Shown right after a public submission. The proposal does NOT exist yet — the
 * citizen must click the link we e-mailed (double opt-in). The `email` query
 * param is bound via withComponentInputBinding.
 */
@Component({
  selector: 'app-public-submission-received-page',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FeedbackMessageComponent, RouterLink, PublicI18nPipe],
  template: `
    <div class="public-result">
      <app-feedback-message
        tone="success"
        [title]="'public.submitProposal.received.title' | t"
        [message]="confirmationMessage()"
      />
      <p class="public-result__note">
        {{ 'public.submitProposal.received.note' | t }}
        <a routerLink="/submit-proposal">{{
          'public.submitProposal.received.noteLink' | t
        }}</a
        >.
      </p>
    </div>
  `,
  styles: `
    .public-result {
      display: grid;
      gap: 1rem;
    }
    .public-result__note {
      margin: 0;
      color: var(--color-muted);
      font-size: 0.9rem;
    }
  `,
})
export class PublicSubmissionReceivedPageComponent {
  private readonly i18n = inject(PublicI18nService);

  /** Bound from ?email=… */
  readonly email = input<string>('');

  protected confirmationMessage(): string {
    const email = this.email();
    // Two entries rather than an optional fragment: naming the address changes
    // the shape of the sentence, not just a slot inside it.
    return email
      ? this.i18n.t('public.submitProposal.received.messageTo', { email })
      : this.i18n.t('public.submitProposal.received.message');
  }
}
