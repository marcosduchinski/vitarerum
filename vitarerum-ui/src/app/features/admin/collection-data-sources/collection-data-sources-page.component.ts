import { DOCUMENT } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  resource,
  signal,
} from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { ApiError, toApiError } from '@core/http/api-error.model';
import { ErrorMessageComponent } from '@shared/components/error-message/error-message.component';
import { LoadingStateComponent } from '@shared/components/loading-state/loading-state.component';
import { PageHeaderComponent } from '@shared/components/page-header/page-header.component';

import { CollectionDataSource, SourceDocument } from '../models/collection-data-source.model';
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

  protected readonly actionError = signal<ApiError | null>(null);
  protected readonly busy = signal(false);

  protected toggle(collection: CollectionDataSource): void {
    this.actionError.set(null);
    this.selectedId.update((current) => (current === collection.id ? null : collection.id));
  }

  protected curatorLabel(collection: CollectionDataSource): string {
    if (collection.curators.length === 0) return 'No curator assigned';
    return collection.curators.map((curator) => curator.name ?? curator.permissionId).join(', ');
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
