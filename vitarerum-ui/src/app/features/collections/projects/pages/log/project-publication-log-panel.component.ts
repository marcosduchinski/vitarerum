import { DOCUMENT, isPlatformBrowser } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  input,
  PLATFORM_ID,
  resource,
  signal,
} from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { IDENTITY_SERVICE } from '@core/auth/identity.service';
import { ApiError, toApiError } from '@core/http/api-error.model';
import { EmptyStateComponent } from '@shared/components/empty-state/empty-state.component';
import { ErrorMessageComponent } from '@shared/components/error-message/error-message.component';
import { LoadingStateComponent } from '@shared/components/loading-state/loading-state.component';

import { Attachment, PublicationLogEntry } from '../../models/project.model';
import { PROJECT_API_SERVICE } from '../../services/project-api.service';

// Groups that may add publication entries once the project is COMPLETED.
const PUBLICATION_STAFF_GROUPS = ['CURATORIAL', 'COLLECTIONS_MANAGEMENT', 'DIRECTION'] as const;

@Component({
  selector: 'app-project-publication-log-panel',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [LoadingStateComponent, ErrorMessageComponent, EmptyStateComponent],
  templateUrl: './project-publication-log-panel.component.html',
  styleUrl: './project-publication-log-panel.component.scss',
})
export class ProjectPublicationLogPanelComponent {
  private readonly projectService = inject(PROJECT_API_SERVICE);
  private readonly identity = inject(IDENTITY_SERVICE);
  private readonly platformId = inject(PLATFORM_ID);
  private readonly document = inject(DOCUMENT);

  readonly projectId = input.required<string>();

  protected readonly publicationResource = resource({
    params: () => ({ projectId: this.projectId() }),
    loader: ({ params }) =>
      firstValueFrom(this.projectService.listPublicationEntries(params.projectId)),
  });
  protected readonly projectResource = resource({
    params: () => ({ projectId: this.projectId() }),
    loader: ({ params }) => firstValueFrom(this.projectService.getProject(params.projectId)),
  });

  protected readonly entries = computed(() => this.publicationResource.value()?.content ?? []);
  protected readonly publicationLog = computed(
    () => this.publicationResource.value()?.publicationLog ?? null,
  );
  protected readonly project = computed(() => this.projectResource.value() ?? null);
  protected readonly group = computed(() => this.identity.session()?.group ?? null);
  protected readonly isExternalResearcher = computed(() => this.group() === 'EXTERNAL');
  protected readonly projectStatus = computed(() => this.project()?.status ?? null);

  // The publication log inverts the usual gate: the external requester writes
  // while IN_PROGRESS; publication staff write once COMPLETED.
  protected readonly canWriteEntries = computed(() => {
    const status = this.projectStatus();
    const group = this.group();
    if (!status || !group) return false;
    if (status === 'IN_PROGRESS') return group === 'EXTERNAL';
    if (status === 'COMPLETED')
      return (PUBLICATION_STAFF_GROUPS as readonly string[]).includes(group);
    return false;
  });
  protected readonly publicationLockMessage = computed(() => {
    const status = this.projectStatus();
    if (!status || this.canWriteEntries()) return null;
    if (status !== 'IN_PROGRESS' && status !== 'COMPLETED') {
      return 'Publication entries are available while the project is in progress or completed.';
    }
    if (this.isExternalResearcher()) {
      return 'Researcher publication entries are only available while the project is in progress.';
    }
    return 'Staff publication entries are only available once the project is completed.';
  });

  protected readonly publicationError = computed<ApiError | null>(() => {
    const err = this.publicationResource.error();
    return err ? toApiError(err) : null;
  });
  protected readonly projectError = computed<ApiError | null>(() => {
    const err = this.projectResource.error();
    return err ? toApiError(err) : null;
  });

  // Add-entry form state.
  protected readonly addNote = signal('');
  protected readonly addFiles = signal<readonly File[]>([]);
  protected readonly addSubmitting = signal(false);
  protected readonly addError = signal<ApiError | null>(null);
  protected readonly addFormValid = computed(() => this.addNote().trim().length > 0);

  // Inline edit state.
  protected readonly editingEntryId = signal<string | null>(null);
  protected readonly editNote = signal('');
  protected readonly editSubmitting = signal(false);
  protected readonly editError = signal<ApiError | null>(null);
  protected readonly editFormValid = computed(() => this.editNote().trim().length > 0);

  // Attachment state, keyed by entry id (uploads) or fileReference (downloads).
  protected readonly expandedEntryId = signal<string | null>(null);
  protected readonly attachmentFiles = signal<Record<string, File | null>>({});
  protected readonly attachmentNotes = signal<Record<string, string>>({});
  protected readonly attachmentUploading = signal<Record<string, boolean>>({});
  protected readonly attachmentErrors = signal<Record<string, ApiError | null>>({});
  protected readonly attachmentDownloading = signal<Record<string, boolean>>({});
  protected readonly attachmentDownloadErrors = signal<Record<string, ApiError | null>>({});

  protected onAddNoteInput(event: Event): void {
    this.addNote.set((event.target as HTMLTextAreaElement).value);
  }

  protected onAddFilesInput(event: Event): void {
    this.addFiles.set(Array.from((event.target as HTMLInputElement).files ?? []));
  }

  protected async addEntry(event: Event): Promise<void> {
    event.preventDefault();
    if (!this.addFormValid() || this.addSubmitting() || !this.canWriteEntries()) return;

    this.addSubmitting.set(true);
    this.addError.set(null);
    try {
      const created = await firstValueFrom(
        this.projectService.createPublicationEntry(this.projectId(), {
          note: this.addNote().trim(),
        }),
      );
      for (const file of this.addFiles()) {
        await firstValueFrom(
          this.projectService.uploadPublicationEntryAttachment(
            this.projectId(),
            created.id,
            file,
            'DOCUMENT',
          ),
        );
      }
      this.addNote.set('');
      this.addFiles.set([]);
      this.publicationResource.reload();
    } catch (err) {
      this.addError.set(toApiError(err));
    } finally {
      this.addSubmitting.set(false);
    }
  }

  protected openEdit(entry: PublicationLogEntry): void {
    if (!this.canWriteEntries()) return;
    this.editingEntryId.set(entry.id);
    this.editNote.set(entry.note);
    this.editError.set(null);
  }

  protected closeEdit(): void {
    if (this.editSubmitting()) return;
    this.editingEntryId.set(null);
    this.editError.set(null);
  }

  protected onEditNoteInput(event: Event): void {
    this.editNote.set((event.target as HTMLTextAreaElement).value);
  }

  protected async saveEdit(event: Event): Promise<void> {
    event.preventDefault();
    const entryId = this.editingEntryId();
    if (!entryId || !this.editFormValid() || this.editSubmitting() || !this.canWriteEntries()) {
      return;
    }

    this.editSubmitting.set(true);
    this.editError.set(null);
    try {
      await firstValueFrom(
        this.projectService.updatePublicationEntry(this.projectId(), entryId, {
          note: this.editNote().trim(),
        }),
      );
      this.editingEntryId.set(null);
      this.publicationResource.reload();
    } catch (err) {
      this.editError.set(toApiError(err));
    } finally {
      this.editSubmitting.set(false);
    }
  }

  protected toggleAttachments(entryId: string): void {
    this.expandedEntryId.update((current) => (current === entryId ? null : entryId));
  }

  protected onAttachmentFileInput(entryId: string, event: Event): void {
    this.setEntryRecord(
      this.attachmentFiles,
      entryId,
      (event.target as HTMLInputElement).files?.[0] ?? null,
    );
  }

  protected attachmentNote(entryId: string): string {
    return this.attachmentNotes()[entryId] ?? '';
  }

  protected onAttachmentNoteInput(entryId: string, event: Event): void {
    this.setEntryRecord(this.attachmentNotes, entryId, (event.target as HTMLInputElement).value);
  }

  protected async uploadAttachment(entryId: string, event: Event): Promise<void> {
    event.preventDefault();
    const file = this.attachmentFiles()[entryId];
    if (!file || this.attachmentUploading()[entryId] || !this.canWriteEntries()) return;

    this.setEntryRecord(this.attachmentUploading, entryId, true);
    this.setEntryRecord(this.attachmentErrors, entryId, null);
    try {
      const note = this.attachmentNotes()[entryId]?.trim();
      await firstValueFrom(
        this.projectService.uploadPublicationEntryAttachment(
          this.projectId(),
          entryId,
          file,
          'DOCUMENT',
          note || undefined,
        ),
      );
      this.setEntryRecord(this.attachmentFiles, entryId, null);
      this.setEntryRecord(this.attachmentNotes, entryId, '');
      this.publicationResource.reload();
    } catch (err) {
      this.setEntryRecord(this.attachmentErrors, entryId, toApiError(err));
    } finally {
      this.setEntryRecord(this.attachmentUploading, entryId, false);
    }
  }

  protected async downloadAttachment(entryId: string, attachment: Attachment): Promise<void> {
    const ref = attachment.fileReference;
    if (this.attachmentDownloading()[ref]) return;

    this.setEntryRecord(this.attachmentDownloading, ref, true);
    this.setEntryRecord(this.attachmentDownloadErrors, ref, null);
    try {
      const blob = await firstValueFrom(
        this.projectService.downloadPublicationEntryAttachment(this.projectId(), entryId, ref),
      );
      this.saveBlob(blob, attachment.fileName);
    } catch (err) {
      this.setEntryRecord(this.attachmentDownloadErrors, ref, toApiError(err));
    } finally {
      this.setEntryRecord(this.attachmentDownloading, ref, false);
    }
  }

  protected dateLabel(date: string): string {
    return date.slice(0, 10);
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

  private setEntryRecord<T>(
    state: { update(updateFn: (value: Record<string, T>) => Record<string, T>): void },
    entryId: string,
    value: T,
  ): void {
    state.update((current) => ({ ...current, [entryId]: value }));
  }
}
