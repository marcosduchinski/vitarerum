import { DOCUMENT, isPlatformBrowser } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  inject,
  input,
  PLATFORM_ID,
  signal,
} from '@angular/core';
import { DomSanitizer, SafeResourceUrl } from '@angular/platform-browser';
import { firstValueFrom } from 'rxjs';

import { ApiError, toApiError } from '@core/http/api-error.model';
import { ErrorMessageComponent } from '@shared/components/error-message/error-message.component';

import { Document } from '../../models/proposal.model';
import { formatProposalDetailDateTime } from '../../proposal-detail.presentation';
import { PROPOSAL_API_SERVICE } from '../../services/proposal-api.service';

type PreviewKind = 'pdf' | 'image' | 'unsupported';

const IMAGE_EXTENSIONS = new Set(['jpg', 'jpeg', 'png', 'gif', 'webp']);

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

  protected readonly downloadingId = signal<string | null>(null);
  protected readonly downloadError = signal<ApiError | null>(null);

  protected readonly previewOpen = signal(false);
  protected readonly previewDoc = signal<Document | null>(null);
  protected readonly previewKind = signal<PreviewKind>('unsupported');
  protected readonly previewUrl = signal<SafeResourceUrl | string | null>(null);
  protected readonly loadingPreview = signal(false);
  protected readonly previewError = signal<ApiError | null>(null);

  // The raw object URL, kept separately so it can be revoked (the sanitized
  // SafeResourceUrl can't be passed back to URL.revokeObjectURL).
  private rawPreviewUrl: string | null = null;

  protected typeLabel(type: string): string {
    const words = type.toLowerCase().split('_').filter(Boolean).join(' ');
    return words ? words.charAt(0).toUpperCase() + words.slice(1) : type;
  }

  protected formatDate(value: string): string {
    return formatProposalDetailDateTime(value);
  }

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
