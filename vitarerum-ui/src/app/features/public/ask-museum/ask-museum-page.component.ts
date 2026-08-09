import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { Router } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { TURNSTILE_SITE_KEY } from '@core/config/app-config.model';
import { ApiError, toApiError } from '@core/http/api-error.model';
import { ErrorMessageComponent } from '@shared/components/error-message/error-message.component';
import { PageHeaderComponent } from '@shared/components/page-header/page-header.component';

import { TurnstileComponent } from '../components/turnstile/turnstile.component';
import { MUSEUM_QUESTION_API_SERVICE } from '../services/museum-question-api.service';

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const MAX_IMAGE_COUNT = 10;
const MAX_IMAGE_BYTES = 5 * 1024 * 1024;
const MAX_TOTAL_IMAGE_BYTES = 25 * 1024 * 1024;
const ALLOWED_IMAGE_TYPES = new Set(['image/png', 'image/jpeg']);

/**
 * "Pergunte ao Museu" public form. Scope is deliberately narrow (see the
 * plan's alert copy) — questions outside scope are closed later by staff with
 * an automatic e-mail, not rejected here.
 */
@Component({
  selector: 'app-ask-museum-page',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [PageHeaderComponent, ErrorMessageComponent, TurnstileComponent],
  templateUrl: './ask-museum-page.component.html',
  styleUrl: './ask-museum-page.component.scss',
})
export class AskMuseumPageComponent {
  private readonly museumQuestions = inject(MUSEUM_QUESTION_API_SERVICE);
  private readonly router = inject(Router);

  protected readonly siteKey = inject(TURNSTILE_SITE_KEY);

  private readonly turnstile = viewChild(TurnstileComponent);

  protected readonly name = signal('');
  protected readonly email = signal('');
  protected readonly subject = signal('');
  protected readonly message = signal('');
  protected readonly consent = signal(false);
  // Honeypot: bound to a visually hidden field. Real users leave it empty.
  protected readonly website = signal('');
  protected readonly captchaToken = signal('');
  protected readonly attachments = signal<readonly File[]>([]);

  protected readonly submitted = signal(false);
  protected readonly submitting = signal(false);
  protected readonly submitError = signal<ApiError | null>(null);

  protected readonly nameError = computed(() => this.submitted() && !this.name().trim());
  protected readonly emailError = computed(
    () => this.submitted() && !EMAIL_PATTERN.test(this.email().trim()),
  );
  protected readonly subjectError = computed(() => this.submitted() && !this.subject().trim());
  protected readonly messageError = computed(() => this.submitted() && !this.message().trim());
  protected readonly consentError = computed(() => this.submitted() && !this.consent());
  protected readonly attachmentError = computed(() => {
    const files = this.attachments();
    if (files.length > MAX_IMAGE_COUNT) return `Attach at most ${MAX_IMAGE_COUNT} images.`;
    if (files.some((file) => !ALLOWED_IMAGE_TYPES.has(file.type))) {
      return 'Only PNG and JPEG images are accepted.';
    }
    if (files.some((file) => file.size > MAX_IMAGE_BYTES)) {
      return 'Each image must be 5 MB or smaller.';
    }
    const total = files.reduce((sum, file) => sum + file.size, 0);
    if (total > MAX_TOTAL_IMAGE_BYTES)
      return 'Image attachments must be 25 MB or smaller in total.';
    return '';
  });
  protected readonly attachmentInputHint = computed(() => {
    const files = this.attachments();
    if (!files.length) return 'Optional: up to 10 PNG or JPEG images, 5 MB each, 25 MB total.';
    const total = files.reduce((sum, file) => sum + file.size, 0);
    return `${files.length} image${files.length === 1 ? '' : 's'} selected · ${this.formatBytes(total)} total`;
  });

  // No site key configured → no widget rendered → don't block submission on it
  // (the server still verifies whatever token, or lack of one, it receives).
  protected readonly captchaRequired = computed(() => !!this.siteKey);
  protected readonly captchaError = computed(
    () => this.submitted() && this.captchaRequired() && !this.captchaToken(),
  );

  private readonly isValid = computed(
    () =>
      !!this.name().trim() &&
      EMAIL_PATTERN.test(this.email().trim()) &&
      !!this.subject().trim() &&
      !!this.message().trim() &&
      this.consent() &&
      !this.attachmentError() &&
      (!this.captchaRequired() || !!this.captchaToken()),
  );

  protected onInput(
    field: 'name' | 'email' | 'subject' | 'message' | 'website',
    event: Event,
  ): void {
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
      case 'message':
        this.message.set(value);
        break;
      case 'website':
        this.website.set(value);
        break;
    }
  }

  protected onConsentChange(event: Event): void {
    this.consent.set((event.target as HTMLInputElement).checked);
  }

  protected onAttachmentsChange(event: Event): void {
    const input = event.target as HTMLInputElement;
    this.attachments.set(Array.from(input.files ?? []));
  }

  protected removeAttachment(index: number): void {
    this.attachments.update((files) => files.filter((_, currentIndex) => currentIndex !== index));
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
        this.museumQuestions.submit({
          requesterName: this.name().trim(),
          requesterEmail: this.email().trim(),
          subject: this.subject().trim(),
          message: this.message().trim(),
          consent: this.consent(),
          captchaToken: this.captchaToken(),
          website: this.website(),
          attachments: this.attachments(),
        }),
      );

      await this.router.navigate(['/ask-museum/received'], {
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

  protected formatBytes(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    const mib = bytes / (1024 * 1024);
    if (mib >= 1) return `${mib.toFixed(mib >= 10 ? 0 : 1)} MB`;
    return `${Math.ceil(bytes / 1024)} KB`;
  }
}
