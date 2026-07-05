import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { RouterLink } from '@angular/router';

import { FeedbackMessageComponent } from '@shared/components/feedback-message/feedback-message.component';

/**
 * Shown right after a question is submitted. There is no public follow-up —
 * the reply comes by e-mail (see museum-questions-public-page-plan.md: "nao
 * ha consulta por e-mail", "nao ha thread de conversa").
 */
@Component({
  selector: 'app-ask-museum-received-page',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FeedbackMessageComponent, RouterLink],
  template: `
    <div class="ask-result">
      <app-feedback-message
        tone="success"
        title="Question received"
        [message]="receivedMessage()"
      />
      <p class="ask-result__note">
        We'll reply by e-mail. Didn't mean to send this? No action is needed —
        <a routerLink="/ask-museum">ask another question</a>.
      </p>
    </div>
  `,
  styles: `
    .ask-result {
      display: grid;
      gap: 1rem;
    }
    .ask-result__note {
      margin: 0;
      color: var(--color-muted);
      font-size: 0.9rem;
    }
  `,
})
export class AskMuseumReceivedPageComponent {
  /** Bound from ?email=… */
  readonly email = input<string>('');

  protected receivedMessage(): string {
    const target = this.email() ? ` to ${this.email()}` : '';
    return `Thank you for your question. We've received it and will reply${target} as soon as possible.`;
  }
}
