import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { ApiError, toApiError } from '@core/http/api-error.model';
import { ErrorMessageComponent } from '@shared/components/error-message/error-message.component';
import { PageHeaderComponent } from '@shared/components/page-header/page-header.component';

import { PROPOSAL_API_SERVICE } from '../../services/proposal-api.service';

@Component({
  selector: 'app-proposal-submit-page',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [PageHeaderComponent, ErrorMessageComponent],
  templateUrl: './proposal-submit-page.component.html',
  styleUrl: './proposal-submit-page.component.scss',
})
export class ProposalSubmitPageComponent {
  private readonly proposalService = inject(PROPOSAL_API_SERVICE);
  private readonly router = inject(Router);

  protected readonly recipient = signal('collections@vitarerum.example.com');
  protected readonly subject = signal(
    'Solicitação de acesso à Coleção de Zoologia para fins de investigação',
  );
  protected readonly body = signal(
    'Meu nome é Pedro Silva, sou  estudante de  na Universidade de Coimbra e venho, por este meio, solicitar  a autorização para consultar um objeto pertencente à Coleção de Zoologia desta prestigiada instituição, o lince ibérico. O objetivo desta visita é integrar a análise do referido espécime na investigação de minha tese, orientada pela Dra Maria Catarina. Proponho que a visita ocorra entre os dias 09/06/2026 e 20/06/2026. Cumprimentos. Pedro Silva',
  );

  protected readonly submitted = signal(false);
  protected readonly submitting = signal(false);
  protected readonly submitError = signal<ApiError | null>(null);

  protected readonly recipientError = computed(
    () => this.submitted() && (!this.recipient().trim() || !this.recipient().includes('@')),
  );
  protected readonly subjectError = computed(() => this.submitted() && !this.subject().trim());
  protected readonly bodyError = computed(() => this.submitted() && !this.body().trim());

  private readonly isValid = computed(
    () =>
      !!this.recipient().trim() &&
      this.recipient().includes('@') &&
      !!this.subject().trim() &&
      !!this.body().trim(),
  );

  protected onInput(field: string, event: Event): void {
    const value = (event.target as HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement)
      .value;
    switch (field) {
      case 'recipient':
        this.recipient.set(value);
        break;
      case 'subject':
        this.subject.set(value);
        break;
      case 'body':
        this.body.set(value);
        break;
    }
  }

  protected async submit(event: Event): Promise<void> {
    event.preventDefault();
    this.submitted.set(true);
    if (!this.isValid()) return;

    this.submitting.set(true);
    this.submitError.set(null);

    try {
      // The proposal opens with exactly one message (Business Rule 01): the
      // backend seeds the conversation from these initialMessage* fields, so we
      // send the user's composed email here rather than via a second sendMessage
      // call (which would create a duplicate alongside the auto-seeded message).
      const response = await firstValueFrom(
        this.proposalService.createProposal({
          initialMessageRecipient: this.recipient().trim(),
          initialMessageSubject: this.subject().trim(),
          initialMessageBody: this.body().trim(),
        }),
      );

      await this.router.navigate(['/p/collections/proposals', response.proposal.id], {
        queryParams: {
          returnTo: '/p/collections/proposals/submit',
          returnLabel: 'submit proposal',
        },
      });
    } catch (err) {
      this.submitError.set(toApiError(err));
    } finally {
      this.submitting.set(false);
    }
  }
}
