import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  resource,
  signal,
  viewChild,
} from '@angular/core';
import { Router } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { TURNSTILE_SITE_KEY } from '@core/config/app-config.model';
import { ApiError, toApiError } from '@core/http/api-error.model';
import { ErrorMessageComponent } from '@shared/components/error-message/error-message.component';
import { PageHeaderComponent } from '@shared/components/page-header/page-header.component';
import { UseType } from '@shared/models/collection-use-status.model';

import { TurnstileComponent } from '../components/turnstile/turnstile.component';
import { PUBLIC_DOCUMENT_TEMPLATE_API_SERVICE } from '../services/public-document-template-api.service';
import { PUBLIC_PROPOSAL_API_SERVICE } from '../services/public-proposal-api.service';

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const MAX_DOCUMENTS = 5;
const MAX_DOCUMENT_BYTES = 10 * 1024 * 1024;
const ALLOWED_DOCUMENT_EXTENSIONS = new Set(['pdf', 'jpg', 'jpeg', 'png', 'docx']);
const ALLOWED_DOCUMENT_MIME_TYPES = new Set([
  'application/pdf',
  'image/jpeg',
  'image/png',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
]);

/** The intended-use options offered to a citizen, in display order. */
const USE_TYPE_OPTIONS: readonly { readonly value: UseType; readonly label: string }[] = [
  { value: 'IN_SITU_VISIT', label: 'In-situ visit' },
  { value: 'EXHIBITION', label: 'Exhibition' },
  { value: 'OTHER', label: 'Other' },
];

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
  private readonly documentTemplates = inject(PUBLIC_DOCUMENT_TEMPLATE_API_SERVICE);
  private readonly router = inject(Router);

  protected readonly siteKey = inject(TURNSTILE_SITE_KEY);

  private readonly turnstile = viewChild(TurnstileComponent);

  protected readonly useTypeOptions = USE_TYPE_OPTIONS;

  protected readonly name = signal('');
  protected readonly email = signal('');
  protected readonly subject = signal('');
  protected readonly body = signal('');
  // Empty until the citizen picks one of USE_TYPE_OPTIONS; '' is invalid.
  protected readonly useType = signal<UseType | ''>('');
  // Required proposed period (ISO YYYY-MM-DD); empty is invalid.
  protected readonly proposedBeginDate = signal('');
  protected readonly proposedEndDate = signal('');
  protected readonly documents = signal<readonly File[]>([]);
  protected readonly consent = signal(false);
  // Honeypot: bound to a visually hidden field. Real users leave it empty.
  protected readonly website = signal('');

  protected readonly captchaToken = signal('');

  // Document templates offered for the currently selected use type. Reloads
  // whenever the citizen changes the selection; empty until one is chosen.
  private readonly templatesResource = resource({
    params: () => this.useType(),
    loader: async ({ params }) => {
      if (!params) return [];
      return firstValueFrom(this.documentTemplates.listTemplates(params));
    },
  });
  protected readonly templates = computed(() => this.templatesResource.value() ?? []);
  protected readonly unsupportedUseTypeSelected = computed(
    () => this.useType() === 'EXHIBITION' || this.useType() === 'OTHER',
  );

  protected templateDownloadUrl(id: string): string {
    return this.documentTemplates.downloadUrl(id);
  }

  protected readonly submitted = signal(false);
  protected readonly submitting = signal(false);
  protected readonly submitError = signal<ApiError | null>(null);

  // Submission-independent variant of dateRangeError, used to gate submit.
  private readonly hasInvalidDateRange = computed(
    () =>
      !!this.proposedBeginDate() &&
      !!this.proposedEndDate() &&
      this.proposedEndDate() < this.proposedBeginDate(),
  );

  private readonly documentValidationError = computed(() => {
    const documents = this.documents();
    if (documents.length === 0) {
      return 'Attach at least one supporting document.';
    }
    if (documents.length > MAX_DOCUMENTS) {
      return 'Attach no more than five supporting documents.';
    }
    const oversized = documents.find((document) => document.size > MAX_DOCUMENT_BYTES);
    if (oversized) {
      return `${oversized.name} is larger than 10 MB.`;
    }
    const unsupported = documents.find((document) => !this.isAllowedDocument(document));
    if (unsupported) {
      return `${unsupported.name} is not a supported file type.`;
    }
    return null;
  });

  protected readonly nameError = computed(() => this.submitted() && !this.name().trim());
  protected readonly emailError = computed(
    () => this.submitted() && !EMAIL_PATTERN.test(this.email().trim()),
  );
  protected readonly subjectError = computed(() => this.submitted() && !this.subject().trim());
  protected readonly bodyError = computed(() => this.submitted() && !this.body().trim());
  protected readonly useTypeError = computed(() => this.submitted() && !this.useType());
  protected readonly beginDateError = computed(() => this.submitted() && !this.proposedBeginDate());
  protected readonly endDateError = computed(() => this.submitted() && !this.proposedEndDate());
  // When both dates are present the end must not precede the begin (ISO
  // YYYY-MM-DD strings compare lexicographically).
  protected readonly dateRangeError = computed(
    () => this.submitted() && this.hasInvalidDateRange(),
  );
  protected readonly documentsError = computed(
    () => this.submitted() && this.documentValidationError() !== null,
  );
  protected readonly documentValidationMessage = computed(() => this.documentValidationError());
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
      !!this.useType() &&
      !!this.proposedBeginDate() &&
      !!this.proposedEndDate() &&
      !this.hasInvalidDateRange() &&
      this.documentValidationError() === null &&
      this.consent() &&
      (!this.captchaRequired() || !!this.captchaToken()),
  );

  protected onInput(
    field:
      'name' | 'email' | 'subject' | 'body' | 'website' | 'proposedBeginDate' | 'proposedEndDate',
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
      case 'body':
        this.body.set(value);
        break;
      case 'website':
        this.website.set(value);
        break;
      case 'proposedBeginDate':
        this.proposedBeginDate.set(value);
        break;
      case 'proposedEndDate':
        this.proposedEndDate.set(value);
        break;
    }
  }

  protected onUseTypeChange(event: Event): void {
    this.useType.set((event.target as HTMLSelectElement).value as UseType | '');
  }

  protected onConsentChange(event: Event): void {
    this.consent.set((event.target as HTMLInputElement).checked);
  }

  protected onDocumentsSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    this.documents.set(Array.from(input.files ?? []));
  }

  protected removeDocument(index: number): void {
    this.documents.update((files) => files.filter((_, current) => current !== index));
  }

  protected formatFileSize(size: number): string {
    if (size < 1024 * 1024) {
      return `${Math.max(1, Math.round(size / 1024))} KB`;
    }
    return `${(size / (1024 * 1024)).toFixed(1)} MB`;
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
          // isValid() guarantees a non-empty selection before we get here.
          useType: this.useType() as UseType,
          // isValid() guarantees both dates are present and in order here.
          proposedBeginDate: this.proposedBeginDate(),
          proposedEndDate: this.proposedEndDate(),
          documents: this.documents(),
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

  private isAllowedDocument(document: File): boolean {
    const extension = document.name.split('.').pop()?.toLowerCase() ?? '';
    return (
      ALLOWED_DOCUMENT_EXTENSIONS.has(extension) ||
      (!!document.type && ALLOWED_DOCUMENT_MIME_TYPES.has(document.type))
    );
  }
}
