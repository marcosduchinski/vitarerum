import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  signal,
} from '@angular/core';
import { FormField, form, required, validate } from '@angular/forms/signals';
import { Router, RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { ButtonDirective } from 'primeng/button';
import { ApiError, toApiError } from '@core/http/api-error.model';
import { USER_MANAGEMENT_SERVICE } from '@features/admin/services/user-management.service';
import { CreateUserPayload } from '@core/auth/models/user.model';
import { passwordPolicyError } from '@core/auth/password-policy.util';
import { ErrorMessageComponent } from '@shared/components/error-message/error-message.component';
import { FormFieldComponent } from '@shared/components/form-field/form-field.component';
import { PageHeaderComponent } from '@shared/components/page-header/page-header.component';

interface UserFormModel {
  readonly name: string;
  readonly email: string;
  readonly password: string;
}

const EMPTY_FORM: UserFormModel = { name: '', email: '', password: '' };

// Permissive client-side check; the server remains the source of truth.
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

@Component({
  selector: 'app-user-new',
  standalone: true,
  imports: [
    RouterLink,
    FormField,
    ButtonDirective,
    ErrorMessageComponent,
    FormFieldComponent,
    PageHeaderComponent,
  ],
  templateUrl: './user-new.component.html',
  styleUrl: './user-new.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class UserNewComponent {
  private readonly userService = inject(USER_MANAGEMENT_SERVICE);
  private readonly router = inject(Router);

  protected readonly formModel = signal<UserFormModel>({ ...EMPTY_FORM });

  // Signal Forms is experimental in Angular 21. Kept local to this route-level
  // form so a future API change has a contained migration surface.
  protected readonly userForm = form(this.formModel, (path) => {
    required(path.name, { message: 'Name is required.' });
    required(path.email, { message: 'Email is required.' });
    validate(path.email, ({ value }) => {
      const email = value().trim();
      return email && !EMAIL_PATTERN.test(email)
        ? { kind: 'invalid-email', message: 'Enter a valid email address.' }
        : undefined;
    });
    required(path.password, { message: 'Password is required.' });
    validate(path.password, ({ value }) => {
      const error = passwordPolicyError(value());
      return error ? { kind: 'weak-password', message: error } : undefined;
    });
  });

  protected readonly pending = signal(false);
  protected readonly saveError = signal<ApiError | null>(null);

  protected readonly saveDisabled = computed(
    () => this.pending() || this.userForm().invalid(),
  );

  protected async save(event: Event): Promise<void> {
    event.preventDefault();
    this.userForm().markAsTouched();
    if (this.saveDisabled()) return;

    const payload = this.buildPayload();
    this.pending.set(true);
    this.saveError.set(null);
    try {
      const created = await firstValueFrom(this.userService.createUser(payload));
      // Land on the new user's detail page so groups can be assigned right away.
      await this.router.navigate(['/p/admin/users', created.id]);
    } catch (err) {
      this.saveError.set(toApiError(err));
    } finally {
      this.pending.set(false);
    }
  }

  protected cancel(): void {
    if (this.pending()) return;
    void this.router.navigate(['/p/admin/users']);
  }

  private buildPayload(): CreateUserPayload {
    const value = this.formModel();
    return {
      name: value.name.trim(),
      email: value.email.trim(),
      password: value.password,
    };
  }
}
