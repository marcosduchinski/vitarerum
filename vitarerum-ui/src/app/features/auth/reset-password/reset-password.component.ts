import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { HttpErrorResponse } from '@angular/common/http';
import { FormField, form, required, validate } from '@angular/forms/signals';
import { ActivatedRoute, RouterLink } from '@angular/router';

import { IDENTITY_SERVICE } from '@core/auth/identity.service';
import { passwordPolicyError } from '@core/auth/password-policy.util';
import { ApiError, toApiError } from '@core/http/api-error.model';
import { ErrorMessageComponent } from '@shared/components/error-message/error-message.component';
import { LogoMarkComponent } from '@shared/components/logo-mark/logo-mark.component';

interface ResetPasswordFormModel {
  readonly newPassword: string;
  readonly confirmPassword: string;
}

const EMPTY_FORM: ResetPasswordFormModel = { newPassword: '', confirmPassword: '' };

@Component({
  selector: 'app-reset-password',
  standalone: true,
  imports: [FormField, RouterLink, ErrorMessageComponent, LogoMarkComponent],
  templateUrl: './reset-password.component.html',
  styleUrl: './reset-password.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ResetPasswordComponent {
  private readonly identity = inject(IDENTITY_SERVICE);
  private readonly route = inject(ActivatedRoute);

  private readonly token = this.route.snapshot.queryParamMap.get('token');
  // A missing token can't be recovered from on this page — send the user
  // straight to request a fresh one instead of showing a dead form.
  protected readonly hasToken = this.token !== null && this.token !== '';

  protected readonly formModel = signal<ResetPasswordFormModel>({ ...EMPTY_FORM });

  protected readonly resetPasswordForm = form(this.formModel, (path) => {
    required(path.newPassword, { message: 'New password is required.' });
    validate(path.newPassword, ({ value }) => {
      const error = passwordPolicyError(value());
      return error ? { kind: 'weak-password', message: error } : undefined;
    });

    required(path.confirmPassword, { message: 'Confirm the new password.' });
    validate(path.confirmPassword, ({ value, valueOf }) => {
      const confirm = value();
      return confirm && confirm !== valueOf(path.newPassword)
        ? { kind: 'password-mismatch', message: 'Passwords do not match.' }
        : undefined;
    });
  });

  protected readonly pending = signal(false);
  protected readonly submitted = signal(false);
  // Opaque per the backend contract: an invalid, expired, or already-used
  // token all surface as the same 404 — never distinguish which.
  protected readonly tokenRejected = signal(false);
  protected readonly submitError = signal<ApiError | null>(null);

  protected readonly submitDisabled = computed(
    () => this.pending() || this.resetPasswordForm().invalid(),
  );

  protected async submit(event: Event): Promise<void> {
    event.preventDefault();
    this.resetPasswordForm().markAsTouched();
    if (this.submitDisabled() || this.token === null) return;

    this.pending.set(true);
    this.submitError.set(null);
    this.tokenRejected.set(false);
    try {
      await this.identity.confirmPasswordReset({
        token: this.token,
        newPassword: this.formModel().newPassword,
      });
      // The backend invalidates every token issued before this instant. If
      // this browser happened to still hold a local session (its own, or a
      // stale one from before), drop it too rather than leaving the UI
      // showing a signed-in state until some later request 401s.
      this.identity.signOut();
      this.submitted.set(true);
    } catch (err) {
      if (err instanceof HttpErrorResponse && err.status === 404) {
        this.tokenRejected.set(true);
      } else {
        this.submitError.set(toApiError(err));
      }
    } finally {
      this.pending.set(false);
    }
  }
}
