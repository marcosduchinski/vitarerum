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
import { ConfirmModalComponent } from '@shared/components/confirm-modal/confirm-modal.component';
import { EmptyStateComponent } from '@shared/components/empty-state/empty-state.component';
import { ErrorMessageComponent } from '@shared/components/error-message/error-message.component';
import { LoadingStateComponent } from '@shared/components/loading-state/loading-state.component';
import { ObjectReference } from '@shared/models/object-reference.model';

import {
  Attachment,
  CollectionUseProjectObject,
  ObjectLogEntriesPage,
  ObjectLogEntry,
  UpdateObjectLogEntryRequest,
} from '../../models/project.model';
import { PROJECT_API_SERVICE } from '../../services/project-api.service';

/**
 * One project object with every access registered against it.
 *
 * The register records accesses, not objects: the same object is handled as
 * many times as the work requires, and each access prints its own RAIS line.
 */
interface AccessObjectRow {
  readonly key: string;
  readonly collectionUseObjectId: string;
  readonly objectReference: ObjectReference;
  readonly entries: readonly ObjectLogEntry[];
  readonly totalObjects: number;
  // Entries left behind by an object that was removed from the project. The
  // RAIS renderer drops them, so they are shown read-only rather than lost.
  readonly orphan: boolean;
}

// The listing is paginated, but the rows are grouped by object: a partial page
// would split a group. Read every page instead, up to the same cap the RAIS
// renderer uses, so screen and document agree.
const ENTRY_PAGE_SIZE = 100;
const ENTRY_CAP = 1000;

@Component({
  selector: 'app-project-object-log-panel',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    LoadingStateComponent,
    ErrorMessageComponent,
    EmptyStateComponent,
    ConfirmModalComponent,
  ],
  templateUrl: './project-object-log-panel.component.html',
  styleUrl: './project-object-log-panel.component.scss',
})
export class ProjectObjectLogPanelComponent {
  private readonly projectService = inject(PROJECT_API_SERVICE);
  private readonly identity = inject(IDENTITY_SERVICE);
  private readonly platformId = inject(PLATFORM_ID);
  private readonly document = inject(DOCUMENT);

  readonly projectId = input.required<string>();

  protected readonly logResource = resource({
    params: () => ({ projectId: this.projectId() }),
    loader: ({ params }) => this.loadEveryEntry(params.projectId),
  });
  protected readonly projectResource = resource({
    params: () => ({ projectId: this.projectId() }),
    loader: ({ params }) => firstValueFrom(this.projectService.getProject(params.projectId)),
  });
  protected readonly logEntries = computed(() => this.logResource.value()?.content ?? []);
  protected readonly accessLog = computed(() => this.logResource.value()?.accessLog ?? null);
  protected readonly project = computed(() => this.projectResource.value() ?? null);
  protected readonly projectObjects = computed(() => this.project()?.objects ?? []);
  protected readonly accessRows = computed(() =>
    // Until the project detail lands, its object list is unknown rather than
    // empty — entries must not be reported as belonging to removed objects.
    this.buildAccessObjectRows(this.projectObjects(), this.logEntries(), this.project() !== null),
  );
  protected readonly entriesTruncated = computed(
    () => (this.logResource.value()?.totalElements ?? 0) > this.logEntries().length,
  );
  protected readonly isExternalResearcher = computed(
    () => this.identity.session()?.group === 'EXTERNAL',
  );
  protected readonly projectInProgress = computed(() => this.project()?.status === 'IN_PROGRESS');
  protected readonly logConcluded = computed(() => !!this.accessLog()?.dateConclusion);
  protected readonly canEditObjectEntries = computed(
    () => !this.logConcluded() && (!this.isExternalResearcher() || this.projectInProgress()),
  );
  protected readonly objectAccessMessage = computed(() => {
    if (this.logConcluded()) {
      return 'This access log is concluded; its entries can no longer be changed.';
    }
    if (this.isExternalResearcher() && this.project() && !this.projectInProgress()) {
      return 'Researcher entries are only available while the project is in progress.';
    }
    return null;
  });
  protected readonly documentDownloading = signal(false);
  protected readonly documentError = signal<ApiError | null>(null);
  protected readonly canDownloadDocument = computed(
    () =>
      !this.logResource.isLoading() &&
      !this.logError() &&
      !!this.accessLog() &&
      this.logEntries().length > 0 &&
      !this.documentDownloading() &&
      !this.hasObjectDraftChanges(),
  );
  // The document is rendered from persisted entries, so drafts would silently
  // be left out of it.
  protected readonly documentBlockedMessage = computed(() =>
    this.hasObjectDraftChanges() ? 'Save your changes before downloading the form.' : null,
  );
  protected readonly logError = computed<ApiError | null>(() => {
    const err = this.logResource.error();
    return err ? toApiError(err) : null;
  });
  protected readonly projectError = computed<ApiError | null>(() => {
    const err = this.projectResource.error();
    return err ? toApiError(err) : null;
  });
  protected readonly objectDraftAddedAt = signal<Record<string, string>>({});
  protected readonly objectDraftNumberOfObjects = signal<Record<string, number>>({});
  protected readonly objectDraftObservations = signal<Record<string, string>>({});
  protected readonly objectSaveSubmitting = signal(false);
  protected readonly objectSaveError = signal<ApiError | null>(null);
  protected readonly objectRowsValid = computed(() =>
    this.logEntries().every(
      (entry) =>
        this.draftAddedAt(entry).trim().length > 0 && this.draftNumberOfObjects(entry) >= 1,
    ),
  );
  protected readonly hasObjectDraftChanges = computed(() =>
    this.logEntries().some((entry) => this.isObjectEntryDirty(entry)),
  );
  protected readonly objectAttachmentFiles = signal<Record<string, File | null>>({});
  protected readonly objectAttachmentDescriptions = signal<Record<string, string>>({});
  protected readonly objectAttachmentUploading = signal<Record<string, boolean>>({});
  protected readonly objectAttachmentErrors = signal<Record<string, ApiError | null>>({});
  // Download state is keyed by the attachment's fileReference.
  protected readonly objectAttachmentDownloading = signal<Record<string, boolean>>({});
  protected readonly objectAttachmentDownloadErrors = signal<Record<string, ApiError | null>>({});
  protected readonly objectAttachmentDeleting = signal<Record<string, boolean>>({});
  protected readonly objectAttachmentDeleteErrors = signal<Record<string, ApiError | null>>({});
  protected readonly expandedObjectKey = signal<string | null>(null);
  protected readonly expandedObjectEntryId = signal<string | null>(null);

  // Register-access form, opened from one object's expanded row.
  protected readonly addObjectKey = signal<string | null>(null);
  protected readonly addAddedAt = signal('');
  protected readonly addNumberOfObjects = signal(1);
  protected readonly addObservations = signal('');
  protected readonly addSubmitting = signal(false);
  protected readonly addError = signal<ApiError | null>(null);
  protected readonly addFormValid = computed(
    () => this.addAddedAt().trim().length > 0 && this.addNumberOfObjects() >= 1,
  );

  // Destructive entry deletion is always mediated by the shared confirmation dialog.
  protected readonly deleteCandidate = signal<ObjectLogEntry | null>(null);
  protected readonly deleteSubmitting = signal(false);
  protected readonly deleteError = signal<ApiError | null>(null);

  protected draftAddedAt(entry: ObjectLogEntry): string {
    return this.objectDraftAddedAt()[entry.id] ?? this.dateTimeInputValue(entry.addedAt);
  }

  protected draftNumberOfObjects(entry: ObjectLogEntry): number {
    return this.objectDraftNumberOfObjects()[entry.id] ?? entry.numberOfObjects;
  }

  protected draftObservations(entry: ObjectLogEntry): string {
    return this.objectDraftObservations()[entry.id] ?? entry.observations ?? '';
  }

  protected onObjectAddedAtInput(entryId: string, event: Event): void {
    this.setEntryRecord(this.objectDraftAddedAt, entryId, (event.target as HTMLInputElement).value);
  }

  protected onObjectQuantityInput(entryId: string, event: Event): void {
    const value = Number((event.target as HTMLInputElement).value);
    this.setEntryRecord(
      this.objectDraftNumberOfObjects,
      entryId,
      Number.isFinite(value) ? value : 0,
    );
  }

  protected onObjectObservationsInput(entryId: string, event: Event): void {
    this.setEntryRecord(
      this.objectDraftObservations,
      entryId,
      (event.target as HTMLTextAreaElement).value,
    );
  }

  protected async saveObjectEntries(event: Event): Promise<void> {
    event.preventDefault();
    if (
      this.objectSaveSubmitting() ||
      !this.canEditObjectEntries() ||
      !this.objectRowsValid() ||
      !this.hasObjectDraftChanges()
    ) {
      return;
    }

    const dirtyEntries = this.logEntries().filter((entry) => this.isObjectEntryDirty(entry));
    this.objectSaveSubmitting.set(true);
    this.objectSaveError.set(null);
    try {
      await Promise.all(
        dirtyEntries.map((entry) =>
          firstValueFrom(
            this.projectService.updateObjectLogEntry(
              this.projectId(),
              entry.id,
              this.updateRequestFor(entry),
            ),
          ),
        ),
      );
      this.objectDraftAddedAt.set({});
      this.objectDraftNumberOfObjects.set({});
      this.objectDraftObservations.set({});
      this.logResource.reload();
    } catch (err) {
      this.objectSaveError.set(toApiError(err));
    } finally {
      this.objectSaveSubmitting.set(false);
    }
  }

  protected toggleObjectRow(rowKey: string): void {
    this.expandedObjectKey.update((current) => (current === rowKey ? null : rowKey));
  }

  protected openAddAccess(row: AccessObjectRow): void {
    if (!this.canEditObjectEntries() || row.orphan) return;
    this.expandedObjectKey.set(row.key);
    this.addObjectKey.set(row.key);
    this.addAddedAt.set(this.dateTimeInputValue(new Date().toISOString()));
    this.addNumberOfObjects.set(1);
    this.addObservations.set('');
    this.addError.set(null);
  }

  protected closeAddAccess(): void {
    if (this.addSubmitting()) return;
    this.addObjectKey.set(null);
    this.addError.set(null);
  }

  protected onAddAddedAtInput(event: Event): void {
    this.addAddedAt.set((event.target as HTMLInputElement).value);
  }

  protected onAddQuantityInput(event: Event): void {
    const value = Number((event.target as HTMLInputElement).value);
    this.addNumberOfObjects.set(Number.isFinite(value) ? value : 0);
  }

  protected onAddObservationsInput(event: Event): void {
    this.addObservations.set((event.target as HTMLTextAreaElement).value);
  }

  protected async addAccessEntry(row: AccessObjectRow, event: Event): Promise<void> {
    event.preventDefault();
    if (
      this.addSubmitting() ||
      !this.addFormValid() ||
      !this.canEditObjectEntries() ||
      row.orphan
    ) {
      return;
    }

    const observations = this.addObservations().trim();
    this.addSubmitting.set(true);
    this.addError.set(null);
    try {
      await firstValueFrom(
        this.projectService.createObjectLogEntry(this.projectId(), {
          collectionUseObjectId: row.collectionUseObjectId,
          numberOfObjects: this.addNumberOfObjects(),
          addedAt: this.apiDateTimeValue(this.addAddedAt()),
          ...(observations ? { observations } : {}),
        }),
      );
      this.addObjectKey.set(null);
      this.logResource.reload();
    } catch (err) {
      this.addError.set(toApiError(err));
    } finally {
      this.addSubmitting.set(false);
    }
  }

  protected openDelete(entry: ObjectLogEntry): void {
    if (!this.canEditObjectEntries() || this.deleteSubmitting()) return;
    this.deleteCandidate.set(entry);
    this.deleteError.set(null);
  }

  protected closeDelete(): void {
    if (this.deleteSubmitting()) return;
    this.deleteCandidate.set(null);
    this.deleteError.set(null);
  }

  protected async confirmDelete(): Promise<void> {
    const entry = this.deleteCandidate();
    if (!entry || this.deleteSubmitting() || !this.canEditObjectEntries()) return;

    this.deleteSubmitting.set(true);
    this.deleteError.set(null);
    try {
      await firstValueFrom(this.projectService.deleteObjectLogEntry(this.projectId(), entry.id));
      this.discardEntryDrafts(entry.id);
      this.deleteCandidate.set(null);
      this.logResource.reload();
    } catch (err) {
      this.deleteError.set(toApiError(err));
    } finally {
      this.deleteSubmitting.set(false);
    }
  }

  protected onObjectAttachmentFileInput(entryId: string, event: Event): void {
    this.setEntryRecord(
      this.objectAttachmentFiles,
      entryId,
      (event.target as HTMLInputElement).files?.[0] ?? null,
    );
  }

  protected objectAttachmentDescription(entryId: string): string {
    return this.objectAttachmentDescriptions()[entryId] ?? '';
  }

  protected onObjectAttachmentDescriptionInput(entryId: string, event: Event): void {
    this.setEntryRecord(
      this.objectAttachmentDescriptions,
      entryId,
      (event.target as HTMLInputElement).value,
    );
  }

  protected async uploadObjectAttachment(entryId: string, event: Event): Promise<void> {
    event.preventDefault();
    const file = this.objectAttachmentFiles()[entryId];
    const description = this.objectAttachmentDescription(entryId).trim();
    if (
      !file ||
      !description ||
      this.objectAttachmentUploading()[entryId] ||
      !this.canEditObjectEntries()
    ) {
      return;
    }

    this.setEntryRecord(this.objectAttachmentUploading, entryId, true);
    this.setEntryRecord(this.objectAttachmentErrors, entryId, null);
    try {
      await firstValueFrom(
        this.projectService.uploadLogEntryAttachment(
          this.projectId(),
          entryId,
          file,
          'DOCUMENT',
          description,
        ),
      );
      this.setEntryRecord(this.objectAttachmentFiles, entryId, null);
      this.setEntryRecord(this.objectAttachmentDescriptions, entryId, '');
      this.logResource.reload();
    } catch (err) {
      this.setEntryRecord(this.objectAttachmentErrors, entryId, toApiError(err));
    } finally {
      this.setEntryRecord(this.objectAttachmentUploading, entryId, false);
    }
  }

  protected async downloadObjectAttachment(entryId: string, attachment: Attachment): Promise<void> {
    const ref = attachment.fileReference;
    if (this.objectAttachmentDownloading()[ref]) return;

    this.setEntryRecord(this.objectAttachmentDownloading, ref, true);
    this.setEntryRecord(this.objectAttachmentDownloadErrors, ref, null);
    try {
      const blob = await firstValueFrom(
        this.projectService.downloadLogEntryAttachment(this.projectId(), entryId, ref),
      );
      this.saveBlob(blob, attachment.fileName);
    } catch (err) {
      this.setEntryRecord(this.objectAttachmentDownloadErrors, ref, toApiError(err));
    } finally {
      this.setEntryRecord(this.objectAttachmentDownloading, ref, false);
    }
  }

  protected async deleteObjectAttachment(entryId: string, attachment: Attachment): Promise<void> {
    const ref = attachment.fileReference;
    if (this.objectAttachmentDeleting()[ref] || !this.canEditObjectEntries()) return;

    this.setEntryRecord(this.objectAttachmentDeleting, ref, true);
    this.setEntryRecord(this.objectAttachmentDeleteErrors, ref, null);
    try {
      await firstValueFrom(
        this.projectService.deleteLogEntryAttachment(this.projectId(), entryId, ref),
      );
      this.logResource.reload();
    } catch (err) {
      this.setEntryRecord(this.objectAttachmentDeleteErrors, ref, toApiError(err));
    } finally {
      this.setEntryRecord(this.objectAttachmentDeleting, ref, false);
    }
  }

  protected async downloadObjectAccessLogDocument(): Promise<void> {
    if (!this.canDownloadDocument()) return;

    this.documentDownloading.set(true);
    this.documentError.set(null);
    try {
      const blob = await firstValueFrom(
        this.projectService.downloadObjectAccessLogDocument(this.projectId()),
      );
      this.saveBlob(blob, this.documentFileName());
    } catch (err) {
      this.documentError.set(toApiError(err));
    } finally {
      this.documentDownloading.set(false);
    }
  }

  // Mirrors the filename the endpoint sets on Content-Disposition, which a blob
  // response does not expose.
  private documentFileName(): string {
    const reference = this.accessLog()?.referenceNumber ?? `project-${this.projectId()}`;
    const safeReference = reference.replace(/[^a-zA-Z0-9._-]+/g, '-').replace(/^-+|-+$/g, '');
    return `${safeReference || 'object-access-log'}-RAIS.docx`;
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

  protected toggleObjectAttachments(entryId: string): void {
    this.expandedObjectEntryId.update((current) => (current === entryId ? null : entryId));
  }

  protected dateTimeInputValue(date: string): string {
    return date.slice(0, 16);
  }

  private async loadEveryEntry(projectId: string): Promise<ObjectLogEntriesPage> {
    const first = await firstValueFrom(
      this.projectService.listObjectLogEntries(projectId, { page: 0, size: ENTRY_PAGE_SIZE }),
    );
    const content = [...first.content];
    for (let page = 1; page < first.totalPages && content.length < ENTRY_CAP; page += 1) {
      const next = await firstValueFrom(
        this.projectService.listObjectLogEntries(projectId, { page, size: ENTRY_PAGE_SIZE }),
      );
      if (!next.content.length) break;
      content.push(...next.content);
    }
    return { ...first, content: content.slice(0, ENTRY_CAP) };
  }

  private buildAccessObjectRows(
    objects: readonly CollectionUseProjectObject[],
    entries: readonly ObjectLogEntry[],
    objectsKnown: boolean,
  ): readonly AccessObjectRow[] {
    const entriesByKey = new Map<string, ObjectLogEntry[]>();
    for (const entry of entries) {
      const key = this.objectKey(
        entry.collectionUseObjectId,
        entry.requestedObjectId,
        entry.objectReference.inventoryNumber,
      );
      entriesByKey.set(key, [...(entriesByKey.get(key) ?? []), entry]);
    }

    // The project's own objects drive the rows: an object with no access yet
    // still has to be reachable, and deleting the last entry must not make the
    // object disappear from the register.
    const rows: AccessObjectRow[] = objects.map((object) => {
      const key = this.objectKey(object.id, null, object.inventoryNumber);
      return this.accessRow(key, object.id, this.objectReferenceOf(object), entriesByKey.get(key));
    });

    const claimed = new Set(rows.map((row) => row.key));
    for (const [key, orphanEntries] of entriesByKey) {
      if (claimed.has(key)) continue;
      const [first] = orphanEntries;
      rows.push(
        this.accessRow(
          key,
          first.collectionUseObjectId,
          first.objectReference,
          orphanEntries,
          objectsKnown,
        ),
      );
    }

    return rows;
  }

  private accessRow(
    key: string,
    collectionUseObjectId: string,
    objectReference: ObjectReference,
    entries: readonly ObjectLogEntry[] = [],
    orphan = false,
  ): AccessObjectRow {
    return {
      key,
      collectionUseObjectId,
      objectReference,
      entries,
      totalObjects: entries.reduce((total, entry) => total + entry.numberOfObjects, 0),
      orphan,
    };
  }

  private objectReferenceOf(object: CollectionUseProjectObject): ObjectReference {
    return {
      inventoryNumber: object.inventoryNumber,
      displayTitle: object.displayTitle,
      objectName: object.objectName,
      briefDescriptionSnapshot: object.briefDescriptionSnapshot,
      collectionId: object.collectionId,
      collectionName: object.collectionName,
    };
  }

  private objectKey(
    collectionUseObjectId: string | null | undefined,
    requestedObjectId: string | null | undefined,
    inventoryNumber: string,
  ): string {
    if (collectionUseObjectId) return `collection-use-object:${collectionUseObjectId}`;
    return requestedObjectId ? `requested:${requestedObjectId}` : `inventory:${inventoryNumber}`;
  }

  private discardEntryDrafts(entryId: string): void {
    this.objectDraftAddedAt.update((current) => this.withoutEntry(current, entryId));
    this.objectDraftNumberOfObjects.update((current) => this.withoutEntry(current, entryId));
    this.objectDraftObservations.update((current) => this.withoutEntry(current, entryId));
  }

  private withoutEntry<T>(current: Record<string, T>, entryId: string): Record<string, T> {
    if (!(entryId in current)) return current;
    return Object.fromEntries(Object.entries(current).filter(([key]) => key !== entryId));
  }

  private isObjectEntryDirty(entry: ObjectLogEntry): boolean {
    return (
      this.draftAddedAt(entry) !== this.dateTimeInputValue(entry.addedAt) ||
      this.draftNumberOfObjects(entry) !== entry.numberOfObjects ||
      this.draftObservations(entry) !== (entry.observations ?? '')
    );
  }

  private updateRequestFor(entry: ObjectLogEntry): UpdateObjectLogEntryRequest {
    const addedAt = this.draftAddedAt(entry);
    const numberOfObjects = this.draftNumberOfObjects(entry);
    const observations = this.draftObservations(entry);
    return {
      ...(addedAt !== this.dateTimeInputValue(entry.addedAt)
        ? { addedAt: this.apiDateTimeValue(addedAt) }
        : {}),
      ...(numberOfObjects !== entry.numberOfObjects ? { numberOfObjects } : {}),
      ...(observations !== (entry.observations ?? '')
        ? { observations: observations.trim() ? observations : null }
        : {}),
    };
  }

  private apiDateTimeValue(value: string): string {
    return value.length === 16 ? `${value}:00` : value;
  }

  private setEntryRecord<T>(
    state: { update(updateFn: (value: Record<string, T>) => Record<string, T>): void },
    entryId: string,
    value: T,
  ): void {
    state.update((current) => ({ ...current, [entryId]: value }));
  }
}
