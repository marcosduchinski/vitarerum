import { DOCUMENT } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  resource,
  signal,
} from '@angular/core';
import { IDENTITY_SERVICE } from '@core/auth/identity.service';
import { firstValueFrom } from 'rxjs';

import { ApiError, toApiError } from '@core/http/api-error.model';
import { ErrorMessageComponent } from '@shared/components/error-message/error-message.component';
import { LoadingStateComponent } from '@shared/components/loading-state/loading-state.component';
import { PageHeaderComponent } from '@shared/components/page-header/page-header.component';

import {
  CollectionArea,
  CollectionCurator,
  CollectionDataSource,
  CuratorCandidate,
  SourceDocument,
} from '../models/collection-data-source.model';
import { COLLECTION_DATA_SOURCE_SERVICE } from '../services/collection-data-source.service';

/** Collections grouped under their area, for the hierarchical listing. */
interface AreaGroup {
  readonly areaId: string;
  readonly areaName: string;
  readonly collections: readonly CollectionDataSource[];
}

@Component({
  selector: 'app-collection-data-sources-page',
  standalone: true,
  imports: [PageHeaderComponent, ErrorMessageComponent, LoadingStateComponent],
  templateUrl: './collection-data-sources-page.component.html',
  styleUrl: './collection-data-sources-page.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CollectionDataSourcesPageComponent {
  private readonly service = inject(COLLECTION_DATA_SOURCE_SERVICE);
  private readonly document = inject(DOCUMENT);
  private readonly identity = inject(IDENTITY_SERVICE);

  /** Only SYS_ADMIN administers the collection catalog and its curators;
   * COLLECTIONS_MANAGEMENT/CURATORIAL keep managing documents via `manageable`. */
  protected readonly isSysAdmin = computed(() => this.identity.session()?.group === 'SYS_ADMIN');

  protected readonly collectionsResource = resource({
    loader: () => firstValueFrom(this.service.listCollections()),
  });

  protected readonly loading = computed(() => this.collectionsResource.isLoading());
  protected readonly loadError = computed<ApiError | null>(() => {
    const err = this.collectionsResource.error();
    return err ? toApiError(err) : null;
  });
  protected readonly collections = computed<readonly CollectionDataSource[]>(
    () => this.collectionsResource.value() ?? [],
  );

  /** Collection areas — the create-collection picker and the area
   * management panel below are SYS_ADMIN only, but every staff member sees
   * the area names denormalised on each collection regardless. */
  protected readonly areasResource = resource({
    params: () => this.isSysAdmin(),
    loader: ({ params }) =>
      params ? firstValueFrom(this.service.listAreas()) : Promise.resolve<CollectionArea[]>([]),
  });
  protected readonly areas = computed<readonly CollectionArea[]>(
    () => this.areasResource.value() ?? [],
  );

  /** Collections grouped by area (denormalised area name/id on the
   * collection itself), sorted by area then collection name. */
  protected readonly groupedCollections = computed<readonly AreaGroup[]>(() => {
    const byArea = new Map<string, CollectionDataSource[]>();
    for (const collection of this.collections()) {
      const bucket = byArea.get(collection.areaId);
      if (bucket) bucket.push(collection);
      else byArea.set(collection.areaId, [collection]);
    }
    return Array.from(byArea.entries())
      .map(([areaId, collections]) => ({
        areaId,
        areaName: collections[0].areaName,
        collections: [...collections].sort((a, b) => a.name.localeCompare(b.name)),
      }))
      .sort((a, b) => a.areaName.localeCompare(b.areaName));
  });

  /** The collection whose documents panel is expanded (one at a time). */
  protected readonly selectedId = signal<string | null>(null);

  protected readonly documentsResource = resource({
    params: () => this.selectedId(),
    loader: ({ params }) =>
      params === null
        ? Promise.resolve<SourceDocument[]>([])
        : firstValueFrom(this.service.listDocuments(params)),
  });

  protected readonly documents = computed<readonly SourceDocument[]>(
    () => this.documentsResource.value() ?? [],
  );
  protected readonly documentsLoading = computed(() => this.documentsResource.isLoading());

  /** Curator candidates (CURATORIAL-group permissions) — only SYS_ADMIN may list them. */
  protected readonly curatorCandidatesResource = resource({
    params: () => this.isSysAdmin(),
    loader: ({ params }) =>
      params
        ? firstValueFrom(this.service.listCuratorCandidates())
        : Promise.resolve<CuratorCandidate[]>([]),
  });
  protected readonly curatorCandidates = computed<readonly CuratorCandidate[]>(
    () => this.curatorCandidatesResource.value() ?? [],
  );

  protected readonly actionError = signal<ApiError | null>(null);
  protected readonly busy = signal(false);

  /** New-collection creation form. */
  protected readonly newCollectionName = signal('');
  protected readonly newCollectionAreaId = signal('');

  /** Collection currently being renamed inline (one at a time). */
  protected readonly editingId = signal<string | null>(null);
  protected readonly editName = signal('');

  /** Curator picker selection per expanded collection. */
  protected readonly selectedCandidateId = signal('');

  /** Target area picker for moving the expanded collection. */
  protected readonly moveAreaId = signal('');

  /** Source document currently configuring semantic object columns. */
  protected readonly mappingDocumentId = signal<string | null>(null);
  protected readonly mappingColumnsByDocument = signal<Record<string, readonly string[]>>({});
  protected readonly mappingInventoryColumn = signal('');
  protected readonly mappingTitleColumn = signal('');
  protected readonly mappingObjectNameColumn = signal('');
  protected readonly mappingDescriptionColumns = signal<readonly string[]>([]);

  /** Collection currently showing the "type the name to confirm" remove
   * control (one at a time). */
  protected readonly removingId = signal<string | null>(null);
  protected readonly removeConfirmText = signal('');

  /** New-area creation form. */
  protected readonly newAreaName = signal('');

  /** Area currently being renamed inline (one at a time). */
  protected readonly editingAreaId = signal<string | null>(null);
  protected readonly editAreaName = signal('');

  protected toggle(collection: CollectionDataSource): void {
    this.actionError.set(null);
    this.selectedCandidateId.set('');
    this.moveAreaId.set('');
    this.selectedId.update((current) => (current === collection.id ? null : collection.id));
  }

  protected curatorLabel(collection: CollectionDataSource): string {
    if (collection.curators.length === 0) return 'No curator assigned';
    return collection.curators.map((curator) => curator.name ?? curator.permissionId).join(', ');
  }

  protected availableCandidates(collection: CollectionDataSource): readonly CuratorCandidate[] {
    const assigned = new Set(collection.curators.map((curator) => curator.permissionId));
    return this.curatorCandidates().filter((candidate) => !assigned.has(candidate.permissionId));
  }

  protected async createCollection(): Promise<void> {
    const name = this.newCollectionName().trim();
    const areaId = this.newCollectionAreaId();
    if (!name || !areaId) return;
    await this.run(() => firstValueFrom(this.service.createCollection(name, areaId)));
    this.newCollectionName.set('');
    this.newCollectionAreaId.set('');
  }

  protected startEdit(collection: CollectionDataSource): void {
    this.editingId.set(collection.id);
    this.editName.set(collection.name);
  }

  protected cancelEdit(): void {
    this.editingId.set(null);
  }

  protected async saveEdit(collection: CollectionDataSource): Promise<void> {
    const name = this.editName().trim();
    this.editingId.set(null);
    if (!name || name === collection.name) return;
    await this.run(() => firstValueFrom(this.service.updateCollection(collection.id, { name })));
  }

  /** Moves the expanded collection to a different area — a dedicated
   * action, not a side effect of renaming (mirrors the backend's
   * MoveCollectionToArea use case). */
  protected async moveToArea(collection: CollectionDataSource): Promise<void> {
    const areaId = this.moveAreaId();
    if (!areaId || areaId === collection.areaId) return;
    await this.run(() => firstValueFrom(this.service.moveCollectionToArea(collection.id, areaId)));
    this.moveAreaId.set('');
  }

  protected otherAreas(collection: CollectionDataSource): readonly CollectionArea[] {
    return this.areas().filter((area) => area.id !== collection.areaId);
  }

  protected startRemove(collection: CollectionDataSource): void {
    this.removingId.set(collection.id);
    this.removeConfirmText.set('');
  }

  protected cancelRemove(): void {
    this.removingId.set(null);
    this.removeConfirmText.set('');
  }

  protected removeConfirmMatches(collection: CollectionDataSource): boolean {
    return this.removeConfirmText().trim() === collection.name;
  }

  /** Permanent — cannot be undone. Only enabled once the typed text matches
   * the collection's exact name (see removeConfirmMatches). */
  protected async confirmRemove(collection: CollectionDataSource): Promise<void> {
    if (!this.removeConfirmMatches(collection)) return;
    await this.run(async () => {
      await firstValueFrom(this.service.removeCollection(collection.id));
      if (this.selectedId() === collection.id) this.selectedId.set(null);
      if (this.editingId() === collection.id) this.editingId.set(null);
      this.removingId.set(null);
      this.removeConfirmText.set('');
    });
  }

  protected async assignCurator(collection: CollectionDataSource): Promise<void> {
    const permissionId = this.selectedCandidateId();
    if (!permissionId) return;
    await this.run(() => firstValueFrom(this.service.assignCurator(collection.id, permissionId)));
    this.selectedCandidateId.set('');
  }

  protected async removeCurator(
    collection: CollectionDataSource,
    curator: CollectionCurator,
  ): Promise<void> {
    await this.run(() =>
      firstValueFrom(this.service.removeCurator(collection.id, curator.permissionId)),
    );
  }

  protected async createArea(): Promise<void> {
    const name = this.newAreaName().trim();
    if (!name) return;
    await this.run(() => firstValueFrom(this.service.createArea(name)));
    this.newAreaName.set('');
  }

  protected startEditArea(area: CollectionArea): void {
    this.editingAreaId.set(area.id);
    this.editAreaName.set(area.name);
  }

  protected cancelEditArea(): void {
    this.editingAreaId.set(null);
  }

  protected async saveEditArea(area: CollectionArea): Promise<void> {
    const name = this.editAreaName().trim();
    this.editingAreaId.set(null);
    if (!name || name === area.name) return;
    await this.run(() => firstValueFrom(this.service.updateArea(area.id, name)));
  }

  /** Rejected (409, COLLECTION_AREA_IN_USE) while any collection is still
   * assigned to it — surfaced generically via actionError, same as every
   * other conflict in this page. */
  protected async removeArea(area: CollectionArea): Promise<void> {
    const confirmed = this.document.defaultView?.confirm(
      `Remove the "${area.name}" area? This is only possible while no collection is assigned to it.`,
    );
    if (!confirmed) return;
    await this.run(() => firstValueFrom(this.service.removeArea(area.id)));
  }

  protected async upload(collection: CollectionDataSource, event: Event): Promise<void> {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    input.value = '';
    if (!file) return;
    await this.run(() => firstValueFrom(this.service.upload(collection.id, file)));
  }

  protected async remove(sourceDocument: SourceDocument): Promise<void> {
    const confirmed = this.document.defaultView?.confirm(
      `Delete "${sourceDocument.fileName}" and remove its rows from the object index?`,
    );
    if (!confirmed) return;
    await this.run(() => firstValueFrom(this.service.remove(sourceDocument.id)));
  }

  protected async reindex(sourceDocument: SourceDocument): Promise<void> {
    await this.run(() => firstValueFrom(this.service.reindex(sourceDocument.id)));
  }

  protected mappingColumns(sourceDocument: SourceDocument): readonly string[] {
    return this.mappingColumnsByDocument()[sourceDocument.id] ?? [];
  }

  protected async configureMapping(sourceDocument: SourceDocument): Promise<void> {
    this.mappingDocumentId.set(sourceDocument.id);
    const mapping = sourceDocument.objectMapping;
    this.mappingInventoryColumn.set(mapping?.inventoryNumberColumn ?? '');
    this.mappingTitleColumn.set(mapping?.displayTitleColumn ?? '');
    this.mappingObjectNameColumn.set(mapping?.objectNameColumn ?? '');
    this.mappingDescriptionColumns.set(mapping?.descriptionColumns ?? []);
    if (this.mappingColumnsByDocument()[sourceDocument.id]) return;
    this.busy.set(true);
    this.actionError.set(null);
    try {
      const columns = await firstValueFrom(this.service.listDocumentColumns(sourceDocument.id));
      this.mappingColumnsByDocument.update((current) => ({
        ...current,
        [sourceDocument.id]: columns,
      }));
    } catch (err) {
      this.actionError.set(toApiError(err));
    } finally {
      this.busy.set(false);
    }
  }

  protected cancelMapping(): void {
    this.mappingDocumentId.set(null);
  }

  protected mappingCanSave(): boolean {
    return Boolean(this.mappingInventoryColumn() && this.mappingTitleColumn());
  }

  protected isDescriptionColumnSelected(column: string): boolean {
    return this.mappingDescriptionColumns().includes(column);
  }

  protected toggleDescriptionColumn(column: string, checked: boolean): void {
    this.mappingDescriptionColumns.update((current) => {
      if (checked) {
        return current.includes(column) ? current : [...current, column];
      }
      return current.filter((value) => value !== column);
    });
  }

  protected async saveMapping(sourceDocument: SourceDocument): Promise<void> {
    if (!this.mappingCanSave()) return;
    await this.run(() =>
      firstValueFrom(
        this.service.updateObjectMapping(sourceDocument.id, {
          inventoryNumberColumn: this.mappingInventoryColumn(),
          displayTitleColumn: this.mappingTitleColumn(),
          objectNameColumn: this.mappingObjectNameColumn() || null,
          descriptionColumns: this.mappingDescriptionColumns(),
        }),
      ),
    );
    this.mappingDocumentId.set(null);
  }

  protected formatDate(value: string | null): string {
    if (!value) return '—';
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: 'medium',
      timeStyle: 'short',
    }).format(new Date(value));
  }

  protected documentsColumnCount(collection: CollectionDataSource): number {
    return collection.manageable ? 6 : 5;
  }

  private async run(operation: () => Promise<unknown>): Promise<void> {
    this.busy.set(true);
    this.actionError.set(null);
    try {
      await operation();
      this.documentsResource.reload();
      this.collectionsResource.reload();
      this.areasResource.reload();
    } catch (err) {
      this.actionError.set(toApiError(err));
    } finally {
      this.busy.set(false);
    }
  }
}
