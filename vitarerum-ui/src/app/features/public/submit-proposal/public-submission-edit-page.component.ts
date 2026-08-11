import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { ApiError, toApiError } from '@core/http/api-error.model';
import { ErrorMessageComponent } from '@shared/components/error-message/error-message.component';
import { FeedbackMessageComponent } from '@shared/components/feedback-message/feedback-message.component';
import { LoadingStateComponent } from '@shared/components/loading-state/loading-state.component';
import { PageHeaderComponent } from '@shared/components/page-header/page-header.component';

import { PublicI18nPipe } from '../i18n/public-i18n.pipe';
import { PublicI18nService } from '../i18n/public-i18n.service';
import {
  PublicAmendmentCorrectionItem,
  PublicAmendmentDocument,
  PublicAmendmentView,
} from '../models/public-proposal.model';
import { PUBLIC_PROPOSAL_API_SERVICE } from '../services/public-proposal-api.service';

const MAX_DOCUMENT_BYTES = 10 * 1024 * 1024;
const ALLOWED_DOCUMENT_EXTENSIONS = new Set(['pdf', 'jpg', 'jpeg', 'png', 'docx']);
const ALLOWED_DOCUMENT_MIME_TYPES = new Set([
  'application/pdf',
  'image/jpeg',
  'image/png',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
]);

type EditState = 'loading' | 'ready' | 'submitted' | 'invalid' | 'conflict';

@Component({
  selector: 'app-public-submission-edit-page',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    ErrorMessageComponent,
    FeedbackMessageComponent,
    LoadingStateComponent,
    PageHeaderComponent,
    RouterLink,
    PublicI18nPipe,
  ],
  templateUrl: './public-submission-edit-page.component.html',
  styleUrl: './public-submission-edit-page.component.scss',
})
export class PublicSubmissionEditPageComponent {
  private readonly publicProposals = inject(PUBLIC_PROPOSAL_API_SERVICE);
  private readonly route = inject(ActivatedRoute);
  private readonly i18n = inject(PublicI18nService);

  private readonly token = this.route.snapshot.queryParamMap.get('token') ?? '';

  protected readonly state = signal<EditState>('loading');
  protected readonly amendment = signal<PublicAmendmentView | null>(null);
  protected readonly selectedFiles = signal<Record<string, File | null>>({});
  protected readonly actionError = signal<ApiError | null>(null);
  protected readonly loadingError = signal<ApiError | null>(null);
  protected readonly busyKey = signal<string | null>(null);
  protected readonly submitting = signal(false);

  protected readonly pendingItems = computed(
    () => this.amendment()?.correctionItems.filter((item) => item.status === 'REQUESTED') ?? [],
  );

  protected readonly hasPendingItems = computed(() => this.pendingItems().length > 0);

  constructor() {
    void this.load();
  }

  protected documentFor(item: PublicAmendmentCorrectionItem): PublicAmendmentDocument | null {
    if (!item.documentId) return null;
    return this.amendment()?.documents.find((document) => document.id === item.documentId) ?? null;
  }

  protected documentsForType(documentType: string): readonly PublicAmendmentDocument[] {
    return this.amendment()?.documents.filter((document) => document.type === documentType) ?? [];
  }

  protected selectedFile(itemId: string): File | null {
    return this.selectedFiles()[itemId] ?? null;
  }

  protected onFileSelected(itemId: string, event: Event): void {
    const input = event.target as HTMLInputElement;
    this.selectedFiles.update((files) => ({
      ...files,
      [itemId]: input.files?.[0] ?? null,
    }));
  }

  protected async upload(item: PublicAmendmentCorrectionItem): Promise<void> {
    const file = this.selectedFile(item.id);
    if (!file || !this.isAllowedDocument(file)) return;

    this.actionError.set(null);
    this.busyKey.set(`upload:${item.id}`);
    try {
      const document = await firstValueFrom(
        this.publicProposals.addAmendmentDocument(this.token, item.documentType, file),
      );
      this.amendment.update((current) =>
        current ? { ...current, documents: [...current.documents, document] } : current,
      );
      this.selectedFiles.update((files) => ({ ...files, [item.id]: null }));
    } catch (err) {
      this.actionError.set(toApiError(err));
    } finally {
      this.busyKey.set(null);
    }
  }

  protected async removeDocument(document: PublicAmendmentDocument): Promise<void> {
    this.actionError.set(null);
    this.busyKey.set(`delete:${document.id}`);
    try {
      await firstValueFrom(this.publicProposals.deleteAmendmentDocument(this.token, document.id));
      this.amendment.update((current) =>
        current
          ? {
              ...current,
              documents: current.documents.filter((candidate) => candidate.id !== document.id),
            }
          : current,
      );
    } catch (err) {
      this.actionError.set(toApiError(err));
    } finally {
      this.busyKey.set(null);
    }
  }

  protected async submit(): Promise<void> {
    this.actionError.set(null);
    this.submitting.set(true);
    try {
      await firstValueFrom(this.publicProposals.submitAmendment(this.token));
      this.state.set('submitted');
    } catch (err) {
      this.actionError.set(toApiError(err));
    } finally {
      this.submitting.set(false);
    }
  }

  protected fileValidationMessage(file: File | null): string | null {
    if (!file) return null;
    if (file.size > MAX_DOCUMENT_BYTES) {
      return this.i18n.t('public.submitProposal.edit.file.tooLarge', { name: file.name });
    }
    if (!this.isAllowedDocument(file)) {
      return this.i18n.t('public.submitProposal.edit.file.invalidType', { name: file.name });
    }
    return null;
  }

  /**
   * Backend status codes are open-ended, so an unknown one falls back to the
   * raw code rather than to an empty span.
   */
  protected statusLabel(status: string): string {
    const key = `public.submitProposal.statuses.${status}`;
    const label = this.i18n.t(key);
    return label === key ? status : label;
  }

  protected formatDate(value: string): string {
    return this.i18n.formatDate(value, { dateStyle: 'medium', timeStyle: 'short' });
  }

  private async load(): Promise<void> {
    if (!this.token) {
      this.state.set('invalid');
      return;
    }
    try {
      this.amendment.set(await firstValueFrom(this.publicProposals.getAmendment(this.token)));
      this.state.set('ready');
    } catch (err) {
      const apiError = toApiError(err);
      this.loadingError.set(apiError);
      this.state.set(apiError.kind === 'conflict' ? 'conflict' : 'invalid');
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
