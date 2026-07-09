import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { FormField, form, required, validate } from '@angular/forms/signals';
import { RouterLink } from '@angular/router';

import { IDENTITY_SERVICE } from '@core/auth/identity.service';
import { ApiError, toApiError } from '@core/http/api-error.model';
import { ErrorMessageComponent } from '@shared/components/error-message/error-message.component';
import { LogoMarkComponent } from '@shared/components/logo-mark/logo-mark.component';

interface ForgotPasswordFormModel {
  readonly email: string;
}

// Permissive client-side check; the server remains the source of truth.
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

@Component({
  selector: 'app-forgot-password',
  standalone: true,
  imports: [FormField, RouterLink, ErrorMessageComponent, LogoMarkComponent],
  templateUrl: './forgot-password.component.html',
  styleUrl: './forgot-password.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ForgotPasswordComponent {
  private readonly identity = inject(IDENTITY_SERVICE);

  protected readonly formModel = signal<ForgotPasswordFormModel>({ email: '' });

  protected readonly forgotPasswordForm = form(this.formModel, (path) => {
    required(path.email, { message: 'Email is required.' });
    validate(path.email, ({ value }) => {
      const email = value().trim();
      return email && !EMAIL_PATTERN.test(email)
        ? { kind: 'invalid-email', message: 'Enter a valid email address.' }
        : undefined;
    });
  });

  protected readonly pending = signal(false);
  protected readonly submitError = signal<ApiError | null>(null);
  // Set once a request completes without error — the same generic message
  // shows whether or not the address has an account, so a submitter can't
  // learn which e-mails exist from the response.
  protected readonly submitted = signal(false);

  protected readonly submitDisabled = computed(
    () => this.pending() || this.forgotPasswordForm().invalid(),
  );

  protected async submit(event: Event): Promise<void> {
    event.preventDefault();
    this.forgotPasswordForm().markAsTouched();
    if (this.submitDisabled()) return;

    this.pending.set(true);
    this.submitError.set(null);
    try {
      await this.identity.requestPasswordReset({ email: this.formModel().email.trim() });
      this.submitted.set(true);
    } catch (err) {
      this.submitError.set(toApiError(err));
    } finally {
      this.pending.set(false);
    }
  }
}
