import { ChangeDetectionStrategy, Component, inject, input } from '@angular/core';
import { RouterLink } from '@angular/router';

import { FeedbackMessageComponent } from '@shared/components/feedback-message/feedback-message.component';

import { PublicI18nPipe } from '../i18n/public-i18n.pipe';
import { PublicI18nService } from '../i18n/public-i18n.service';

/**
 * Shown right after a question is submitted. There is no public follow-up —
 * the reply comes by e-mail (see museum-questions-public-page-plan.md: "nao
 * ha consulta por e-mail", "nao ha thread de conversa").
 */
@Component({
  selector: 'app-ask-museum-received-page',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FeedbackMessageComponent, RouterLink, PublicI18nPipe],
  template: `
    <div class="ask-result">
      <app-feedback-message
        tone="success"
        [title]="'public.askMuseum.received.title' | t"
        [message]="receivedMessage()"
      />
      <p class="ask-result__note">
        {{ 'public.askMuseum.received.note' | t }}
        <a routerLink="/ask-museum">{{ 'public.askMuseum.received.noteLink' | t }}</a
        >.
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
  private readonly i18n = inject(PublicI18nService);

  /** Bound from ?email=… */
  readonly email = input<string>('');

  protected receivedMessage(): string {
    const email = this.email();
    // Two entries rather than an optional fragment: naming the address changes
    // the shape of the sentence, not just a slot inside it.
    return email
      ? this.i18n.t('public.askMuseum.received.messageTo', { email })
      : this.i18n.t('public.askMuseum.received.message');
  }
}
