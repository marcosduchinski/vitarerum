import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { FormField, form, required, validate } from '@angular/forms/signals';
import { Router } from '@angular/router';
import { ButtonDirective } from 'primeng/button';

import { IDENTITY_SERVICE } from '@core/auth/identity.service';
import { passwordPolicyError } from '@core/auth/password-policy.util';
import { ApiError, toApiError } from '@core/http/api-error.model';
import { ErrorMessageComponent } from '@shared/components/error-message/error-message.component';
import { FormFieldComponent } from '@shared/components/form-field/form-field.component';
import { PageHeaderComponent } from '@shared/components/page-header/page-header.component';

interface ChangePasswordFormModel {
  readonly currentPassword: string;
  readonly newPassword: string;
  readonly confirmPassword: string;
}

const EMPTY_FORM: ChangePasswordFormModel = {
  currentPassword: '',
  newPassword: '',
  confirmPassword: '',
};

@Component({
  selector: 'app-change-password',
  standalone: true,
  imports: [
    FormField,
    ButtonDirective,
    ErrorMessageComponent,
    FormFieldComponent,
    PageHeaderComponent,
  ],
  templateUrl: './change-password.component.html',
  styleUrl: './change-password.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ChangePasswordComponent {
  private readonly identity = inject(IDENTITY_SERVICE);
  private readonly router = inject(Router);

  protected readonly formModel = signal<ChangePasswordFormModel>({ ...EMPTY_FORM });

  // Signal Forms is experimental in Angular 21. Kept local to this route-level
  // form so a future API change has a contained migration surface.
  protected readonly changePasswordForm = form(this.formModel, (path) => {
    required(path.currentPassword, { message: 'Current password is required.' });

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
  protected readonly saveError = signal<ApiError | null>(null);

  protected readonly saveDisabled = computed(
    () => this.pending() || this.changePasswordForm().invalid(),
  );

  protected async submit(event: Event): Promise<void> {
    event.preventDefault();
    this.changePasswordForm().markAsTouched();
    if (this.saveDisabled()) return;

    const value = this.formModel();
    this.pending.set(true);
    this.saveError.set(null);
    try {
      await this.identity.changePassword({
        currentPassword: value.currentPassword,
        newPassword: value.newPassword,
      });
      // The backend just invalidated every token issued before this instant,
      // including the one this session is using — sign out locally too and
      // require a fresh login rather than limping on a now-rejected token.
      this.identity.signOut();
      await this.router.navigate(['/login'], {
        queryParams: { message: 'password-changed' },
      });
    } catch (err) {
      this.saveError.set(toApiError(err));
    } finally {
      this.pending.set(false);
    }
  }
}
