import { ChangeDetectionStrategy, Component, computed, inject, signal, viewChild } from '@angular/core';
import { Router } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { TURNSTILE_SITE_KEY } from '@core/config/app-config.model';
import { ApiError, toApiError } from '@core/http/api-error.model';
import { ErrorMessageComponent } from '@shared/components/error-message/error-message.component';
import { PageHeaderComponent } from '@shared/components/page-header/page-header.component';

import { TurnstileComponent } from '../components/turnstile/turnstile.component';
import { PUBLIC_PROPOSAL_API_SERVICE } from '../services/public-proposal-api.service';

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

@Component({
  selector: 'app-public-submit-proposal-page',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [PageHeaderComponent, ErrorMessageComponent, TurnstileComponent],
  templateUrl: './public-submit-proposal-page.component.html',
  styleUrl: './public-submit-proposal-page.component.scss',
})
export class PublicSubmitProposalPageComponent {
  private readonly publicProposals = inject(PUBLIC_PROPOSAL_API_SERVICE);
  private readonly router = inject(Router);

  protected readonly siteKey = inject(TURNSTILE_SITE_KEY);

  private readonly turnstile = viewChild(TurnstileComponent);

  protected readonly name = signal('');
  protected readonly email = signal('');
  protected readonly subject = signal('');
  protected readonly body = signal('');
  protected readonly consent = signal(false);
  // Honeypot: bound to a visually hidden field. Real users leave it empty.
  protected readonly website = signal('');

  protected readonly captchaToken = signal('');

  protected readonly submitted = signal(false);
  protected readonly submitting = signal(false);
  protected readonly submitError = signal<ApiError | null>(null);

  protected readonly nameError = computed(() => this.submitted() && !this.name().trim());
  protected readonly emailError = computed(
    () => this.submitted() && !EMAIL_PATTERN.test(this.email().trim()),
  );
  protected readonly subjectError = computed(() => this.submitted() && !this.subject().trim());
  protected readonly bodyError = computed(() => this.submitted() && !this.body().trim());
  protected readonly consentError = computed(() => this.submitted() && !this.consent());
  protected readonly captchaError = computed(
    () => this.submitted() && this.captchaRequired() && !this.captchaToken(),
  );

  // No site key configured → no widget rendered → don't block submission on it
  // (the server still verifies whatever token, or lack of one, it receives).
  protected readonly captchaRequired = computed(() => !!this.siteKey);

  private readonly isValid = computed(
    () =>
      !!this.name().trim() &&
      EMAIL_PATTERN.test(this.email().trim()) &&
      !!this.subject().trim() &&
      !!this.body().trim() &&
      this.consent() &&
      (!this.captchaRequired() || !!this.captchaToken()),
  );

  protected onInput(field: 'name' | 'email' | 'subject' | 'body' | 'website', event: Event): void {
    const value = (event.target as HTMLInputElement | HTMLTextAreaElement).value;
    switch (field) {
      case 'name':
        this.name.set(value);
        break;
      case 'email':
        this.email.set(value);
        break;
      case 'subject':
        this.subject.set(value);
        break;
      case 'body':
        this.body.set(value);
        break;
      case 'website':
        this.website.set(value);
        break;
    }
  }

  protected onConsentChange(event: Event): void {
    this.consent.set((event.target as HTMLInputElement).checked);
  }

  protected onVerified(token: string): void {
    this.captchaToken.set(token);
  }

  protected onCaptchaInvalidated(): void {
    this.captchaToken.set('');
  }

  protected async submit(event: Event): Promise<void> {
    event.preventDefault();
    this.submitted.set(true);
    if (!this.isValid()) return;

    this.submitting.set(true);
    this.submitError.set(null);

    try {
      const receipt = await firstValueFrom(
        this.publicProposals.submit({
          citizenName: this.name().trim(),
          citizenEmail: this.email().trim(),
          subject: this.subject().trim(),
          body: this.body().trim(),
          consent: this.consent(),
          captchaToken: this.captchaToken(),
          website: this.website(),
        }),
      );

      await this.router.navigate(['/submit-proposal/received'], {
        queryParams: { email: receipt.email },
      });
    } catch (err) {
      this.submitError.set(toApiError(err));
      // The single-use token is now spent; re-arm the widget for a retry.
      this.captchaToken.set('');
      this.turnstile()?.reset();
    } finally {
      this.submitting.set(false);
    }
  }
}
