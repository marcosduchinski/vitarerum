import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  resource,
  signal,
} from '@angular/core';
import { Router } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { ApiError, toApiError } from '@core/http/api-error.model';
import { PUBLIC_DOCUMENT_TEMPLATE_API_SERVICE } from '@features/public/services/public-document-template-api.service';
import { ErrorMessageComponent } from '@shared/components/error-message/error-message.component';
import { PageHeaderComponent } from '@shared/components/page-header/page-header.component';
import { UseType } from '@shared/models/collection-use-status.model';

import { PROPOSAL_API_SERVICE } from '../../services/proposal-api.service';

const MAX_DOCUMENTS = 5;
const MAX_DOCUMENT_BYTES = 10 * 1024 * 1024;
const ALLOWED_DOCUMENT_EXTENSIONS = new Set(['pdf', 'jpg', 'jpeg', 'png', 'docx']);
const ALLOWED_DOCUMENT_MIME_TYPES = new Set([
  'application/pdf',
  'image/jpeg',
  'image/png',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
]);

const USE_TYPE_OPTIONS: readonly { readonly value: UseType; readonly label: string }[] = [
  { value: 'IN_SITU_VISIT', label: 'In-situ visit' },
  { value: 'EXHIBITION', label: 'Exhibition' },
  { value: 'OTHER', label: 'Other' },
];

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
  private readonly documentTemplates = inject(PUBLIC_DOCUMENT_TEMPLATE_API_SERVICE);
  private readonly router = inject(Router);

  protected readonly useTypeOptions = USE_TYPE_OPTIONS;

  protected readonly useType = signal<UseType | ''>('');
  protected readonly proposedBeginDate = signal('');
  protected readonly proposedEndDate = signal('');
  protected readonly subject = signal(
    'Solicitação de acesso à Coleção de Zoologia para fins de investigação',
  );
  protected readonly body = signal(
    'Meu nome é Pedro Silva, sou  estudante de  na Universidade de Coimbra e venho, por este meio, solicitar  a autorização para consultar um objeto pertencente à Coleção de Zoologia desta prestigiada instituição, o lince ibérico. O objetivo desta visita é integrar a análise do referido espécime na investigação de minha tese, orientada pela Dra Maria Catarina. Proponho que a visita ocorra entre os dias 09/06/2026 e 20/06/2026. Cumprimentos. Pedro Silva',
  );
  protected readonly documents = signal<readonly File[]>([]);

  protected readonly submitted = signal(false);
  protected readonly submitting = signal(false);
  protected readonly submitError = signal<ApiError | null>(null);

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

  protected readonly useTypeError = computed(() => this.submitted() && !this.useType());
  protected readonly unsupportedUseTypeError = computed(
    () => this.submitted() && this.unsupportedUseTypeSelected(),
  );
  protected readonly beginDateError = computed(() => this.submitted() && !this.proposedBeginDate());
  protected readonly endDateError = computed(() => this.submitted() && !this.proposedEndDate());
  protected readonly dateRangeError = computed(
    () => this.submitted() && this.hasInvalidDateRange(),
  );
  protected readonly subjectError = computed(() => this.submitted() && !this.subject().trim());
  protected readonly bodyError = computed(() => this.submitted() && !this.body().trim());
  protected readonly documentsError = computed(
    () => this.submitted() && this.documentValidationError() !== null,
  );
  protected readonly documentValidationMessage = computed(() => this.documentValidationError());

  private readonly isValid = computed(
    () =>
      !!this.useType() &&
      !this.unsupportedUseTypeSelected() &&
      !!this.proposedBeginDate() &&
      !!this.proposedEndDate() &&
      !this.hasInvalidDateRange() &&
      !!this.subject().trim() &&
      !!this.body().trim() &&
      this.documentValidationError() === null,
  );

  protected onInput(field: string, event: Event): void {
    const value = (event.target as HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement)
      .value;
    switch (field) {
      case 'subject':
        this.subject.set(value);
        break;
      case 'body':
        this.body.set(value);
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

  protected onDocumentsSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    this.documents.set(Array.from(input.files ?? []));
  }

  protected removeDocument(index: number, input?: HTMLInputElement): void {
    this.documents.update((files) => files.filter((_, current) => current !== index));
    if (input) input.value = '';
  }

  protected formatFileSize(size: number): string {
    if (size < 1024 * 1024) {
      return `${Math.max(1, Math.round(size / 1024))} KB`;
    }
    return `${(size / (1024 * 1024)).toFixed(1)} MB`;
  }

  protected templateDownloadUrl(id: string): string {
    return this.documentTemplates.downloadUrl(id);
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
          intendedUse: this.useType() as UseType,
          beginDate: this.proposedBeginDate(),
          endDate: this.proposedEndDate(),
          initialMessageSubject: this.subject().trim(),
          initialMessageBody: this.body().trim(),
          documents: this.documents(),
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

  private isAllowedDocument(document: File): boolean {
    const extension = document.name.split('.').pop()?.toLowerCase() ?? '';
    return (
      ALLOWED_DOCUMENT_EXTENSIONS.has(extension) ||
      (!!document.type && ALLOWED_DOCUMENT_MIME_TYPES.has(document.type))
    );
  }
}
