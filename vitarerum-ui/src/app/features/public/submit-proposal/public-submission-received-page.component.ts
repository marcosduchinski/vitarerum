import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { RouterLink } from '@angular/router';

import { FeedbackMessageComponent } from '@shared/components/feedback-message/feedback-message.component';

/**
 * Shown right after a public submission. The proposal does NOT exist yet — the
 * citizen must click the link we e-mailed (double opt-in). The `email` query
 * param is bound via withComponentInputBinding.
 */
@Component({
  selector: 'app-public-submission-received-page',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FeedbackMessageComponent, RouterLink],
  template: `
    <div class="public-result">
      <app-feedback-message
        tone="success"
        title="Almost there — check your inbox"
        [message]="confirmationMessage()"
      />
      <p class="public-result__note">
        Didn't get the e-mail? It can take a few minutes. Check your spam folder, or
        <a routerLink="/submit-proposal">start a new request</a>.
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
  /** Bound from ?email=… */
  readonly email = input<string>('');

  protected confirmationMessage(): string {
    const target = this.email() ? ` to ${this.email()}` : '';
    return `We've sent a confirmation link${target}. Click it to forward your request to the collections team. The link expires in 24 hours.`;
  }
}
