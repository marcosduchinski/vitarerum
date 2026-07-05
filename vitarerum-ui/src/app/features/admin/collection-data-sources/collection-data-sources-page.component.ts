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
  CollectionCurator,
  CollectionDataSource,
  CuratorCandidate,
  SourceDocument,
} from '../models/collection-data-source.model';
import { COLLECTION_DATA_SOURCE_SERVICE } from '../services/collection-data-source.service';

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

  /** Collection currently being renamed inline (one at a time). */
  protected readonly editingId = signal<string | null>(null);
  protected readonly editName = signal('');

  /** Curator picker selection per expanded collection. */
  protected readonly selectedCandidateId = signal('');

  /** Collection currently showing the "type the name to confirm" remove
   * control (one at a time). */
  protected readonly removingId = signal<string | null>(null);
  protected readonly removeConfirmText = signal('');

  protected toggle(collection: CollectionDataSource): void {
    this.actionError.set(null);
    this.selectedCandidateId.set('');
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
    if (!name) return;
    await this.run(() => firstValueFrom(this.service.createCollection(name)));
    this.newCollectionName.set('');
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
    await this.run(
      () => firstValueFrom(this.service.removeCurator(collection.id, curator.permissionId)),
    );
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

  protected formatDate(value: string | null): string {
    if (!value) return '—';
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: 'medium',
      timeStyle: 'short',
    }).format(new Date(value));
  }

  private async run(operation: () => Promise<unknown>): Promise<void> {
    this.busy.set(true);
    this.actionError.set(null);
    try {
      await operation();
      this.documentsResource.reload();
      this.collectionsResource.reload();
    } catch (err) {
      this.actionError.set(toApiError(err));
    } finally {
      this.busy.set(false);
    }
  }
}
