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

import { Attachment, ObjectLogEntry, ObjectOccurrenceEntry } from '../../models/project.model';
import { PROJECT_API_SERVICE } from '../../services/project-api.service';

interface OccurrenceObjectRow {
  readonly key: string;
  readonly objectReference: ObjectLogEntry['objectReference'];
  readonly requestedObjectId: string | null;
  readonly numberOfObjects: number;
  readonly accessEntries: readonly ObjectLogEntry[];
  readonly occurrences: readonly ObjectOccurrenceEntry[];
}

@Component({
  selector: 'app-project-occurrence-log-panel',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [LoadingStateComponent, ErrorMessageComponent, EmptyStateComponent],
  templateUrl: './project-occurrence-log-panel.component.html',
  styleUrl: './project-occurrence-log-panel.component.scss',
})
export class ProjectOccurrenceLogPanelComponent {
  private readonly projectService = inject(PROJECT_API_SERVICE);
  private readonly identity = inject(IDENTITY_SERVICE);
  private readonly platformId = inject(PLATFORM_ID);
  private readonly document = inject(DOCUMENT);

  readonly projectId = input.required<string>();

  protected readonly occurrenceResource = resource({
    params: () => ({ projectId: this.projectId() }),
    loader: ({ params }) =>
      firstValueFrom(this.projectService.listObjectOccurrenceEntries(params.projectId)),
  });
  protected readonly accessResource = resource({
    params: () => ({ projectId: this.projectId() }),
    loader: ({ params }) =>
      firstValueFrom(this.projectService.listObjectLogEntries(params.projectId)),
  });
  protected readonly projectResource = resource({
    params: () => ({ projectId: this.projectId() }),
    loader: ({ params }) => firstValueFrom(this.projectService.getProject(params.projectId)),
  });
  protected readonly accessLogEntries = computed(() => this.accessResource.value()?.content ?? []);
  protected readonly occurrenceEntries = computed(
    () => this.occurrenceResource.value()?.content ?? [],
  );
  protected readonly occurrenceObjectRows = computed(() =>
    this.buildOccurrenceObjectRows(this.accessLogEntries(), this.occurrenceEntries()),
  );
  protected readonly occurrenceLog = computed(
    () => this.occurrenceResource.value()?.occurrenceLog ?? null,
  );
  protected readonly project = computed(() => this.projectResource.value() ?? null);
  protected readonly isExternalResearcher = computed(
    () => this.identity.session()?.group === 'EXTERNAL',
  );
  protected readonly projectInProgress = computed(() => this.project()?.status === 'IN_PROGRESS');
  protected readonly canAddOccurrenceEntries = computed(
    () => !this.isExternalResearcher() || this.projectInProgress(),
  );
  protected readonly occurrenceAccessMessage = computed(() => {
    if (this.isExternalResearcher() && this.project() && !this.projectInProgress()) {
      return 'Researcher occurrence reports are only available while the project is in progress.';
    }
    return null;
  });
  protected readonly occurrenceError = computed<ApiError | null>(() => {
    const err = this.occurrenceResource.error();
    return err ? toApiError(err) : null;
  });
  protected readonly accessError = computed<ApiError | null>(() => {
    const err = this.accessResource.error();
    return err ? toApiError(err) : null;
  });
  protected readonly projectError = computed<ApiError | null>(() => {
    const err = this.projectResource.error();
    return err ? toApiError(err) : null;
  });
  protected readonly canDownloadDocxDemo = computed(
    () =>
      !this.occurrenceResource.isLoading() &&
      !this.occurrenceError() &&
      !!this.occurrenceLog() &&
      this.occurrenceEntries().length > 0,
  );
  protected readonly expandedObjectKey = signal<string | null>(null);
  protected readonly selectedOccurrenceObjectKey = signal<string | null>(null);
  protected readonly selectedOccurrenceObject = computed(() => {
    const key = this.selectedOccurrenceObjectKey();
    return key ? (this.occurrenceObjectRows().find((row) => row.key === key) ?? null) : null;
  });
  protected readonly editingOccurrenceEntryId = signal<string | null>(null);
  protected readonly editingOccurrenceEntry = computed(() => {
    const entryId = this.editingOccurrenceEntryId();
    return entryId
      ? (this.occurrenceEntries().find((entry) => entry.id === entryId) ?? null)
      : null;
  });
  protected readonly occurrenceDate = signal('');
  protected readonly occurrenceLocation = signal('');
  protected readonly occurrenceDescription = signal('');
  protected readonly occurrenceTestimonial = signal('');
  protected readonly occurrenceFiles = signal<readonly File[]>([]);
  protected readonly occurrenceSubmitting = signal(false);
  protected readonly occurrenceSubmitError = signal<ApiError | null>(null);
  protected readonly occurrenceFormValid = computed(
    () =>
      !!this.selectedOccurrenceObject() &&
      this.occurrenceDate().trim().length > 0 &&
      this.occurrenceLocation().trim().length > 0 &&
      this.occurrenceDescription().trim().length > 0,
  );
  protected readonly occurrenceEditNumberOfObjects = signal(1);
  protected readonly occurrenceEditDate = signal('');
  protected readonly occurrenceEditLocation = signal('');
  protected readonly occurrenceEditDescription = signal('');
  protected readonly occurrenceEditTestimonial = signal('');
  protected readonly occurrenceEditSubmitting = signal(false);
  protected readonly occurrenceEditError = signal<ApiError | null>(null);
  protected readonly occurrenceEditFormValid = computed(
    () =>
      !!this.editingOccurrenceEntry() &&
      this.occurrenceEditNumberOfObjects() >= 1 &&
      this.occurrenceEditDate().trim().length > 0 &&
      this.occurrenceEditLocation().trim().length > 0 &&
      this.occurrenceEditDescription().trim().length > 0,
  );
  protected readonly occurrenceAttachmentFiles = signal<Record<string, File | null>>({});
  protected readonly occurrenceAttachmentUploading = signal<Record<string, boolean>>({});
  protected readonly occurrenceAttachmentErrors = signal<Record<string, ApiError | null>>({});
  // Download state is keyed by the attachment's fileReference.
  protected readonly occurrenceAttachmentDownloading = signal<Record<string, boolean>>({});
  protected readonly occurrenceAttachmentDownloadErrors = signal<Record<string, ApiError | null>>(
    {},
  );
  protected readonly expandedOccurrenceEntryId = signal<string | null>(null);

  protected toggleObjectOccurrences(rowKey: string): void {
    this.expandedObjectKey.update((current) => (current === rowKey ? null : rowKey));
  }

  protected openAddOccurrence(row: OccurrenceObjectRow): void {
    if (!this.canAddOccurrenceEntries()) return;
    this.selectedOccurrenceObjectKey.set(row.key);
    this.occurrenceDate.set('');
    this.occurrenceLocation.set('');
    this.occurrenceDescription.set('');
    this.occurrenceTestimonial.set('');
    this.occurrenceFiles.set([]);
    this.occurrenceSubmitError.set(null);
  }

  protected closeAddOccurrence(): void {
    if (this.occurrenceSubmitting()) return;
    this.selectedOccurrenceObjectKey.set(null);
    this.occurrenceSubmitError.set(null);
  }

  protected openEditOccurrence(entry: ObjectOccurrenceEntry): void {
    if (!this.canAddOccurrenceEntries()) return;
    this.editingOccurrenceEntryId.set(entry.id);
    this.occurrenceEditNumberOfObjects.set(entry.numberOfObjects);
    this.occurrenceEditDate.set(entry.occurrenceDate);
    this.occurrenceEditLocation.set(entry.location);
    this.occurrenceEditDescription.set(entry.detailedDescription);
    this.occurrenceEditTestimonial.set(entry.testimonial ?? '');
    this.occurrenceEditError.set(null);
  }

  protected closeEditOccurrence(): void {
    if (this.occurrenceEditSubmitting()) return;
    this.editingOccurrenceEntryId.set(null);
    this.occurrenceEditError.set(null);
  }

  protected onOccurrenceDateInput(event: Event): void {
    this.occurrenceDate.set((event.target as HTMLInputElement).value);
  }

  protected onOccurrenceLocationInput(event: Event): void {
    this.occurrenceLocation.set((event.target as HTMLInputElement).value);
  }

  protected onOccurrenceDescriptionInput(event: Event): void {
    this.occurrenceDescription.set((event.target as HTMLTextAreaElement).value);
  }

  protected onOccurrenceTestimonialInput(event: Event): void {
    this.occurrenceTestimonial.set((event.target as HTMLTextAreaElement).value);
  }

  protected onOccurrenceFilesInput(event: Event): void {
    this.occurrenceFiles.set(Array.from((event.target as HTMLInputElement).files ?? []));
  }

  protected onOccurrenceEditQuantityInput(event: Event): void {
    const value = Number((event.target as HTMLInputElement).value);
    this.occurrenceEditNumberOfObjects.set(Number.isFinite(value) ? value : 0);
  }

  protected onOccurrenceEditDateInput(event: Event): void {
    this.occurrenceEditDate.set((event.target as HTMLInputElement).value);
  }

  protected onOccurrenceEditLocationInput(event: Event): void {
    this.occurrenceEditLocation.set((event.target as HTMLInputElement).value);
  }

  protected onOccurrenceEditDescriptionInput(event: Event): void {
    this.occurrenceEditDescription.set((event.target as HTMLTextAreaElement).value);
  }

  protected onOccurrenceEditTestimonialInput(event: Event): void {
    this.occurrenceEditTestimonial.set((event.target as HTMLTextAreaElement).value);
  }

  protected async addOccurrenceEntry(event: Event): Promise<void> {
    event.preventDefault();
    const selectedObject = this.selectedOccurrenceObject();
    const occurrenceDate = this.occurrenceDate().trim();
    const location = this.occurrenceLocation().trim();
    const detailedDescription = this.occurrenceDescription().trim();
    const testimonial = this.occurrenceTestimonial().trim();
    if (
      !selectedObject ||
      !this.occurrenceFormValid() ||
      this.occurrenceSubmitting() ||
      !this.canAddOccurrenceEntries()
    ) {
      return;
    }

    this.occurrenceSubmitting.set(true);
    this.occurrenceSubmitError.set(null);
    try {
      const createdEntry = await firstValueFrom(
        this.projectService.createObjectOccurrenceEntry(this.projectId(), {
          inventoryNumber: selectedObject.objectReference.inventoryNumber,
          numberOfObjects: selectedObject.numberOfObjects,
          occurrenceDate,
          location,
          detailedDescription,
          ...(selectedObject.requestedObjectId
            ? { requestedObjectId: selectedObject.requestedObjectId }
            : {}),
          ...(testimonial ? { testimonial } : {}),
        }),
      );
      for (const file of this.occurrenceFiles()) {
        await firstValueFrom(
          this.projectService.uploadOccurrenceEntryAttachment(
            this.projectId(),
            createdEntry.id,
            file,
            'DOCUMENT',
          ),
        );
      }
      this.expandedObjectKey.set(selectedObject.key);
      this.selectedOccurrenceObjectKey.set(null);
      this.occurrenceResource.reload();
    } catch (err) {
      this.occurrenceSubmitError.set(toApiError(err));
    } finally {
      this.occurrenceSubmitting.set(false);
    }
  }

  protected async updateOccurrenceEntry(event: Event): Promise<void> {
    event.preventDefault();
    const entry = this.editingOccurrenceEntry();
    if (
      !entry ||
      !this.occurrenceEditFormValid() ||
      this.occurrenceEditSubmitting() ||
      !this.canAddOccurrenceEntries()
    ) {
      return;
    }

    this.occurrenceEditSubmitting.set(true);
    this.occurrenceEditError.set(null);
    try {
      await firstValueFrom(
        this.projectService.updateObjectOccurrenceEntry(this.projectId(), entry.id, {
          numberOfObjects: this.occurrenceEditNumberOfObjects(),
          occurrenceDate: this.occurrenceEditDate().trim(),
          location: this.occurrenceEditLocation().trim(),
          detailedDescription: this.occurrenceEditDescription().trim(),
          testimonial: this.occurrenceEditTestimonial().trim() || null,
        }),
      );
      this.editingOccurrenceEntryId.set(null);
      this.occurrenceResource.reload();
    } catch (err) {
      this.occurrenceEditError.set(toApiError(err));
    } finally {
      this.occurrenceEditSubmitting.set(false);
    }
  }

  protected onOccurrenceAttachmentFileInput(entryId: string, event: Event): void {
    this.setEntryRecord(
      this.occurrenceAttachmentFiles,
      entryId,
      (event.target as HTMLInputElement).files?.[0] ?? null,
    );
  }

  protected async uploadOccurrenceAttachment(entryId: string, event: Event): Promise<void> {
    event.preventDefault();
    const file = this.occurrenceAttachmentFiles()[entryId];
    if (!file || this.occurrenceAttachmentUploading()[entryId] || !this.canAddOccurrenceEntries()) {
      return;
    }

    this.setEntryRecord(this.occurrenceAttachmentUploading, entryId, true);
    this.setEntryRecord(this.occurrenceAttachmentErrors, entryId, null);
    try {
      await firstValueFrom(
        this.projectService.uploadOccurrenceEntryAttachment(
          this.projectId(),
          entryId,
          file,
          'DOCUMENT',
        ),
      );
      this.setEntryRecord(this.occurrenceAttachmentFiles, entryId, null);
      this.occurrenceResource.reload();
    } catch (err) {
      this.setEntryRecord(this.occurrenceAttachmentErrors, entryId, toApiError(err));
    } finally {
      this.setEntryRecord(this.occurrenceAttachmentUploading, entryId, false);
    }
  }

  protected async downloadOccurrenceAttachment(
    entryId: string,
    attachment: Attachment,
  ): Promise<void> {
    const ref = attachment.fileReference;
    if (this.occurrenceAttachmentDownloading()[ref]) return;

    this.setEntryRecord(this.occurrenceAttachmentDownloading, ref, true);
    this.setEntryRecord(this.occurrenceAttachmentDownloadErrors, ref, null);
    try {
      const blob = await firstValueFrom(
        this.projectService.downloadOccurrenceEntryAttachment(this.projectId(), entryId, ref),
      );
      this.saveBlob(blob, attachment.fileName);
    } catch (err) {
      this.setEntryRecord(this.occurrenceAttachmentDownloadErrors, ref, toApiError(err));
    } finally {
      this.setEntryRecord(this.occurrenceAttachmentDownloading, ref, false);
    }
  }

  protected downloadObjectOccurrenceLogDemo(): void {
    if (!this.canDownloadDocxDemo()) return;

    const blob = new Blob([this.objectOccurrenceLogDemoContent()], {
      type: 'text/plain;charset=utf-8',
    });
    const reference = this.occurrenceLog()?.referenceNumber ?? `project-${this.projectId()}`;
    const safeReference = reference.replace(/[^a-zA-Z0-9._-]+/g, '-').replace(/^-+|-+$/g, '');
    this.saveBlob(blob, `${safeReference || 'object-occurrence-log'}-occurrence-log.docx`);
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

  private objectOccurrenceLogDemoContent(): string {
    const log = this.occurrenceLog();
    const lines = [
      'DEMONSTRATION DOCX EXPORT',
      'This placeholder contains plain text and will be replaced by the document endpoint.',
      '',
      `Log reference: ${log?.referenceNumber ?? 'Not issued'}`,
      `Project ID: ${this.projectId()}`,
      `Curator: ${log?.curator?.user.name ?? '—'}`,
      '',
      'OCCURRENCES',
    ];

    this.occurrenceEntries().forEach((entry, index) => {
      lines.push(
        '',
        `${index + 1}. ${entry.objectReference.inventoryNumber}`,
        `Object: ${entry.objectReference.displayTitle ?? entry.objectReference.objectName ?? '—'}`,
        `Number of objects: ${entry.numberOfObjects}`,
        `Occurrence date: ${entry.occurrenceDate}`,
        `Location: ${entry.location}`,
        `Reported by: ${entry.reportedBy.user.name}`,
        `Description: ${entry.detailedDescription}`,
        `Testimonial: ${entry.testimonial ?? '—'}`,
        `Attachments: ${entry.attachments.length}`,
      );
    });

    return lines.join('\r\n');
  }

  protected toggleOccurrenceAttachments(entryId: string): void {
    this.expandedOccurrenceEntryId.update((current) => (current === entryId ? null : entryId));
  }

  protected dateLabel(date: string): string {
    return date.slice(0, 10);
  }

  private setEntryRecord<T>(
    state: { update(updateFn: (value: Record<string, T>) => Record<string, T>): void },
    entryId: string,
    value: T,
  ): void {
    state.update((current) => ({ ...current, [entryId]: value }));
  }

  private buildOccurrenceObjectRows(
    accessEntries: readonly ObjectLogEntry[],
    occurrenceEntries: readonly ObjectOccurrenceEntry[],
  ): readonly OccurrenceObjectRow[] {
    const occurrencesByObject = new Map<string, ObjectOccurrenceEntry[]>();
    for (const entry of occurrenceEntries) {
      const key = this.objectKey(entry.requestedObjectId, entry.objectReference.inventoryNumber);
      occurrencesByObject.set(key, [...(occurrencesByObject.get(key) ?? []), entry]);
    }

    const rowsByObject = new Map<string, OccurrenceObjectRow>();
    for (const entry of accessEntries) {
      const key = this.objectKey(entry.requestedObjectId, entry.objectReference.inventoryNumber);
      const existing = rowsByObject.get(key);
      if (existing) {
        rowsByObject.set(key, {
          ...existing,
          numberOfObjects: existing.numberOfObjects + entry.numberOfObjects,
          accessEntries: [...existing.accessEntries, entry],
        });
        continue;
      }

      rowsByObject.set(key, {
        key,
        objectReference: entry.objectReference,
        requestedObjectId: entry.requestedObjectId ?? null,
        numberOfObjects: entry.numberOfObjects,
        accessEntries: [entry],
        occurrences: occurrencesByObject.get(key) ?? [],
      });
    }

    return [...rowsByObject.values()].map((row) => ({
      ...row,
      occurrences: occurrencesByObject.get(row.key) ?? [],
    }));
  }

  private objectKey(requestedObjectId: string | null | undefined, inventoryNumber: string): string {
    return requestedObjectId ? `requested:${requestedObjectId}` : `inventory:${inventoryNumber}`;
  }
}
