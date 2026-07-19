import { DomSanitizer, SafeHtml } from '@angular/platform-browser';
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
import { EmptyStateComponent } from '@shared/components/empty-state/empty-state.component';
import { ErrorMessageComponent } from '@shared/components/error-message/error-message.component';
import { LoadingStateComponent } from '@shared/components/loading-state/loading-state.component';
import { PageHeaderComponent } from '@shared/components/page-header/page-header.component';
import { highlightToSafeMarkup } from '@shared/utils/highlight-html.util';

import { ObjectSearchHit, ObjectSearchQuery } from '../../models/object-search.model';
import { OBJECT_SEARCH_SERVICE } from '../../services/object-search.service';

const PAGE_SIZE = 20;

@Component({
  selector: 'app-object-search-page',
  standalone: true,
  imports: [PageHeaderComponent, ErrorMessageComponent, LoadingStateComponent, EmptyStateComponent],
  templateUrl: './object-search-page.component.html',
  styleUrl: './object-search-page.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ObjectSearchPageComponent {
  private readonly service = inject(OBJECT_SEARCH_SERVICE);
  private readonly sanitizer = inject(DomSanitizer);

  protected readonly collectionsResource = resource({
    loader: () => firstValueFrom(this.service.listSearchableCollections()),
  });
  protected readonly collections = computed(() => this.collectionsResource.value() ?? []);

  protected readonly queryDraft = signal('');
  protected readonly appliedQuery = signal('');
  protected readonly collectionFilter = signal('');
  protected readonly currentPage = signal(0);

  protected readonly searchResource = resource({
    params: (): ObjectSearchQuery | undefined => {
      const q = this.appliedQuery().trim();
      return q
        ? {
            q,
            collectionId: this.collectionFilter() || undefined,
            page: this.currentPage(),
            size: PAGE_SIZE,
          }
        : undefined;
    },
    loader: ({ params }) => firstValueFrom(this.service.search(params!)),
  });

  protected readonly hasSearched = computed(() => this.appliedQuery().trim().length > 0);
  protected readonly loading = computed(() => this.searchResource.isLoading());
  protected readonly searchError = computed<ApiError | null>(() => {
    const err = this.searchResource.error();
    return err ? toApiError(err) : null;
  });

  protected readonly items = computed<readonly ObjectSearchHit[]>(
    () => this.searchResource.value()?.items ?? [],
  );
  protected readonly total = computed(() => this.searchResource.value()?.total ?? 0);
  protected readonly totalPages = computed(() => Math.max(1, Math.ceil(this.total() / PAGE_SIZE)));
  protected readonly rangeStart = computed(() =>
    this.total() === 0 ? 0 : this.currentPage() * PAGE_SIZE + 1,
  );
  protected readonly rangeEnd = computed(() =>
    Math.min((this.currentPage() + 1) * PAGE_SIZE, this.total()),
  );

  protected onQueryInput(event: Event): void {
    this.queryDraft.set((event.target as HTMLInputElement).value);
  }

  protected onCollectionChange(event: Event): void {
    this.collectionFilter.set((event.target as HTMLSelectElement).value);
    this.currentPage.set(0);
    if (this.hasSearched()) this.search();
  }

  protected search(): void {
    this.appliedQuery.set(this.queryDraft().trim());
    this.currentPage.set(0);
  }

  protected prevPage(): void {
    this.currentPage.update((p) => Math.max(0, p - 1));
  }

  protected nextPage(): void {
    this.currentPage.update((p) => Math.min(this.totalPages() - 1, p + 1));
  }

  protected highlightHtml(hit: ObjectSearchHit): SafeHtml {
    // Safe: highlightToSafeMarkup() escapes the whole string and only re-opens
    // <mark> for the backend's own <b> markers — never trust hit.highlight raw.
    return this.sanitizer.bypassSecurityTrustHtml(highlightToSafeMarkup(hit.highlight));
  }
}
