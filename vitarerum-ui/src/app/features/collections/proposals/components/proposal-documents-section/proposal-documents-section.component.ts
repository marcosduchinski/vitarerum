import { DOCUMENT, isPlatformBrowser } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  effect,
  inject,
  input,
  output,
  PLATFORM_ID,
  signal,
} from '@angular/core';
import { DomSanitizer, SafeResourceUrl } from '@angular/platform-browser';
import { firstValueFrom } from 'rxjs';

import { ApiError, toApiError } from '@core/http/api-error.model';
import { ProposalStatus } from '@shared/models/collection-use-status.model';
import { ErrorMessageComponent } from '@shared/components/error-message/error-message.component';

import { RequestDocumentCorrectionsRequest } from '../../models/proposal-actions.model';
import { Document, DocumentCorrectionItem } from '../../models/proposal.model';
import { formatProposalDetailDateTime } from '../../proposal-detail.presentation';
import { PROPOSAL_API_SERVICE } from '../../services/proposal-api.service';

type PreviewKind = 'pdf' | 'image' | 'unsupported';

// A correction staged locally before the batch is sent. `documentId` set means a
// flagged existing document; absent means a missing document being requested.
interface CorrectionDraftItem {
  readonly key: string;
  readonly documentType: string;
  readonly reason: string;
  readonly documentId?: string;
  readonly documentName?: string;
}

const IMAGE_EXTENSIONS = new Set(['jpg', 'jpeg', 'png', 'gif', 'webp']);

// The document type is free-form text. Mirrors the String(128) column the
// backend persists it into, so the field can't stage a value the API rejects.
const MAX_DOCUMENT_TYPE_LENGTH = 128;

@Component({
  selector: 'app-proposal-documents-section',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ErrorMessageComponent],
  templateUrl: './proposal-documents-section.component.html',
  styleUrl: './proposal-documents-section.component.scss',
})
export class ProposalDocumentsSectionComponent {
  private readonly proposalService = inject(PROPOSAL_API_SERVICE);
  private readonly sanitizer = inject(DomSanitizer);
  private readonly document = inject(DOCUMENT);
  private readonly platformId = inject(PLATFORM_ID);

  readonly proposalId = input.required<string>();
  readonly documents = input.required<readonly Document[]>();
  readonly status = input.required<ProposalStatus>();
  readonly correctionItems = input<readonly DocumentCorrectionItem[]>([]);
  // Mutation state is owned by the container (the my-detail page), mirroring the
  // conversation section's sendingMessage / messageError / replyResetVersion.
  readonly submittingCorrections = input<boolean>(false);
  readonly correctionError = input<ApiError | null>(null);
  readonly correctionResetVersion = input<number>(0);

  readonly correctionRequestSubmitted = output<RequestDocumentCorrectionsRequest>();

  protected readonly downloadingId = signal<string | null>(null);
  protected readonly downloadError = signal<ApiError | null>(null);

  protected readonly previewOpen = signal(false);
  protected readonly previewDoc = signal<Document | null>(null);
  protected readonly previewKind = signal<PreviewKind>('unsupported');
  protected readonly previewUrl = signal<SafeResourceUrl | string | null>(null);
  protected readonly loadingPreview = signal(false);
  protected readonly previewError = signal<ApiError | null>(null);

  // Correction analysis (local draft)
  protected readonly maxTypeLength = MAX_DOCUMENT_TYPE_LENGTH;
  protected readonly stagedItems = signal<readonly CorrectionDraftItem[]>([]);
  protected readonly note = signal('');
  // Which document's inline "request correction" form is open (its id), and the
  // reason being typed there.
  protected readonly correctionFormDocId = signal<string | null>(null);
  protected readonly correctionReason = signal('');
  protected readonly missingFormOpen = signal(false);
  protected readonly missingType = signal('');
  protected readonly missingReason = signal('');
  // The document row currently highlighted from a "Show document" click in the
  // corrections panel.
  protected readonly highlightedDocId = signal<string | null>(null);

  protected readonly canReview = computed(() => this.status() === 'PENDING');
  protected readonly hasStaged = computed(() => this.stagedItems().length > 0);

  // documentId -> its still-open (REQUESTED) correction, for the row badge.
  protected readonly pendingByDocId = computed(() => {
    const map = new Map<string, DocumentCorrectionItem>();
    for (const item of this.correctionItems()) {
      if (item.status === 'REQUESTED' && item.documentId) map.set(item.documentId, item);
    }
    return map;
  });

  // The full correction history, newest first. The panel is the source of
  // truth (missing requests have no row; a resolved replacement may point at a
  // document the requester has since removed).
  protected readonly sortedCorrections = computed(() =>
    [...this.correctionItems()].sort((a, b) => b.requestedAt.localeCompare(a.requestedAt)),
  );

  // Reset the local draft after the container reports a successful send.
  private readonly resetDraftOnVersionChange = effect(() => {
    if (this.correctionResetVersion() > 0) this.clearDraft();
  });

  // The raw object URL, kept separately so it can be revoked (the sanitized
  // SafeResourceUrl can't be passed back to URL.revokeObjectURL).
  private rawPreviewUrl: string | null = null;

  protected typeLabel(type: string): string {
    // Legacy codes are ALL_CAPS_UNDERSCORE (e.g. PUBLIC_SUBMISSION,
    // REQUESTER_ATTACHMENT) — humanise only those. Free-form text is shown
    // verbatim, including short all-caps like "CV" or "RG" that carry no
    // underscore and must not be lower-cased to "Cv" / "Rg".
    if (!type.includes('_')) return type;
    const words = type.toLowerCase().split('_').filter(Boolean).join(' ');
    return words ? words.charAt(0).toUpperCase() + words.slice(1) : type;
  }

  protected formatDate(value: string): string {
    return formatProposalDetailDateTime(value);
  }

  protected stagedForDoc(documentId: string): boolean {
    return this.stagedItems().some((item) => item.documentId === documentId);
  }

  // The referenced document's file name, if it still exists on the proposal (a
  // resolved replacement may point at a document the requester has since removed).
  protected documentNameFor(documentId: string | undefined): string | null {
    if (!documentId) return null;
    return this.documents().find((doc) => doc.id === documentId)?.fileName ?? null;
  }

  // Highlight + scroll to the document row a correction item points at.
  protected showDocument(documentId: string): void {
    this.highlightedDocId.set(documentId);
    if (!isPlatformBrowser(this.platformId)) return;
    this.document
      .getElementById(`doc-row-${documentId}`)
      ?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }

  // Correction draft actions

  protected openCorrectionForm(doc: Document): void {
    this.correctionFormDocId.set(doc.id);
    this.correctionReason.set('');
  }

  protected cancelCorrectionForm(): void {
    this.correctionFormDocId.set(null);
    this.correctionReason.set('');
  }

  protected onCorrectionReasonInput(event: Event): void {
    this.correctionReason.set((event.target as HTMLTextAreaElement).value);
  }

  protected addCorrection(doc: Document): void {
    const reason = this.correctionReason().trim();
    if (!reason) return;
    this.stagedItems.update((items) => [
      ...items,
      {
        key: `${doc.id}:${Date.now()}`,
        documentType: doc.type,
        reason,
        documentId: doc.id,
        documentName: doc.fileName,
      },
    ]);
    this.cancelCorrectionForm();
  }

  protected openMissingForm(): void {
    this.missingFormOpen.set(true);
    this.missingType.set('');
    this.missingReason.set('');
  }

  protected cancelMissingForm(): void {
    this.missingFormOpen.set(false);
    this.missingType.set('');
    this.missingReason.set('');
  }

  protected onMissingTypeInput(event: Event): void {
    this.missingType.set((event.target as HTMLInputElement).value);
  }

  protected onMissingReasonInput(event: Event): void {
    this.missingReason.set((event.target as HTMLTextAreaElement).value);
  }

  protected addMissing(): void {
    const documentType = this.missingType().trim();
    const reason = this.missingReason().trim();
    if (!documentType || documentType.length > MAX_DOCUMENT_TYPE_LENGTH || !reason) return;
    this.stagedItems.update((items) => [
      ...items,
      { key: `missing:${Date.now()}`, documentType, reason },
    ]);
    this.cancelMissingForm();
  }

  protected removeStaged(key: string): void {
    this.stagedItems.update((items) => items.filter((item) => item.key !== key));
  }

  protected onNoteInput(event: Event): void {
    this.note.set((event.target as HTMLTextAreaElement).value);
  }

  protected send(): void {
    if (!this.hasStaged() || this.submittingCorrections()) return;
    this.correctionRequestSubmitted.emit({
      items: this.stagedItems().map(({ documentType, reason, documentId }) => ({
        documentType,
        reason,
        documentId,
      })),
      note: this.note().trim() || undefined,
    });
  }

  private clearDraft(): void {
    this.stagedItems.set([]);
    this.note.set('');
    this.cancelCorrectionForm();
    this.cancelMissingForm();
  }

  // Preview / download (read-only)

  protected async download(doc: Document): Promise<void> {
    if (this.downloadingId()) return;
    this.downloadingId.set(doc.id);
    this.downloadError.set(null);
    try {
      const blob = await firstValueFrom(
        this.proposalService.downloadDocument(this.proposalId(), doc.id),
      );
      this.saveBlob(blob, doc.fileName);
    } catch (err) {
      this.downloadError.set(toApiError(err));
    } finally {
      this.downloadingId.set(null);
    }
  }

  protected async openPreview(doc: Document): Promise<void> {
    this.revokePreviewUrl();
    const kind = this.kindOf(doc.fileName);
    this.previewDoc.set(doc);
    this.previewKind.set(kind);
    this.previewError.set(null);
    this.previewUrl.set(null);
    this.previewOpen.set(true);

    if (kind === 'unsupported' || !isPlatformBrowser(this.platformId)) return;

    this.loadingPreview.set(true);
    try {
      const blob = await firstValueFrom(
        this.proposalService.downloadDocument(this.proposalId(), doc.id),
      );
      const url = URL.createObjectURL(blob);
      this.rawPreviewUrl = url;
      // A PDF renders in an <iframe>, so its src must be a trusted resource URL.
      this.previewUrl.set(
        kind === 'pdf' ? this.sanitizer.bypassSecurityTrustResourceUrl(url) : url,
      );
    } catch (err) {
      this.previewError.set(toApiError(err));
    } finally {
      this.loadingPreview.set(false);
    }
  }

  protected closePreview(): void {
    this.previewOpen.set(false);
    this.previewDoc.set(null);
    this.previewUrl.set(null);
    this.previewError.set(null);
    this.revokePreviewUrl();
  }

  private kindOf(fileName: string): PreviewKind {
    const extension = fileName.split('.').pop()?.toLowerCase() ?? '';
    if (extension === 'pdf') return 'pdf';
    if (IMAGE_EXTENSIONS.has(extension)) return 'image';
    return 'unsupported';
  }

  private saveBlob(blob: Blob, fileName: string): void {
    if (!isPlatformBrowser(this.platformId)) return;
    const url = URL.createObjectURL(blob);
    const anchor = this.document.createElement('a');
    anchor.href = url;
    anchor.download = fileName;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  private revokePreviewUrl(): void {
    if (this.rawPreviewUrl) {
      URL.revokeObjectURL(this.rawPreviewUrl);
      this.rawPreviewUrl = null;
    }
  }
}
