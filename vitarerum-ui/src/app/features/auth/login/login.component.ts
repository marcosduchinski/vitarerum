import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';

import { IDENTITY_SERVICE } from '@core/auth/identity.service';
import { LogoMarkComponent } from '@shared/components/logo-mark/logo-mark.component';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [LogoMarkComponent, RouterLink],
  templateUrl: './login.component.html',
  styleUrl: './login.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class LoginComponent {
  private readonly identity = inject(IDENTITY_SERVICE);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);

  protected readonly email = signal('alice@ext.example.com');
  protected readonly password = signal('password');
  protected readonly loading = signal(false);
  protected readonly loginError = signal(false);
  private readonly submitted = signal(false);
  private readonly emailTouched = signal(false);
  private readonly passwordTouched = signal(false);

  protected readonly emailRequired = computed(
    () => (this.submitted() || this.emailTouched()) && !this.email(),
  );
  protected readonly emailFormat = computed(
    () =>
      (this.submitted() || this.emailTouched()) && !!this.email() && !this.email().includes('@'),
  );
  protected readonly passwordRequired = computed(
    () => (this.submitted() || this.passwordTouched()) && !this.password(),
  );

  private readonly isValid = computed(
    () => !!this.email() && this.email().includes('@') && !!this.password(),
  );

  protected onEmailInput(event: Event): void {
    this.email.set((event.target as HTMLInputElement).value);
    this.emailTouched.set(true);
  }

  protected onPasswordInput(event: Event): void {
    this.password.set((event.target as HTMLInputElement).value);
    this.passwordTouched.set(true);
  }

  protected async submit(event: Event): Promise<void> {
    event.preventDefault();
    if (this.loading()) return;
    this.submitted.set(true);
    if (!this.isValid()) return;

    this.loading.set(true);
    this.loginError.set(false);

    try {
      await this.identity.signIn({ email: this.email(), password: this.password() });
      const returnUrl = this.route.snapshot.queryParamMap.get('returnUrl');
      const destination = returnUrl?.startsWith('/p/') ? returnUrl : '/p/dashboard';
      await this.router.navigateByUrl(destination);
    } catch {
      this.loginError.set(true);
    } finally {
      this.loading.set(false);
    }
  }
}
