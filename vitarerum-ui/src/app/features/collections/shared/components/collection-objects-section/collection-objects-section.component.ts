import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  input,
  output,
  signal,
} from '@angular/core';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';
import { firstValueFrom } from 'rxjs';

import { ApiError, toApiError } from '@core/http/api-error.model';
import { ObjectSearchHit } from '@features/objects/models/object-search.model';
import { OBJECT_SEARCH_SERVICE } from '@features/objects/services/object-search.service';
import { ConfirmModalComponent } from '@shared/components/confirm-modal/confirm-modal.component';
import { ErrorMessageComponent } from '@shared/components/error-message/error-message.component';
import { highlightToSafeMarkup } from '@shared/utils/highlight-html.util';

import {
  adaptSearchHitToObjectSnapshot,
  ObjectSearchSnapshot,
} from '../../adapters/object-search-snapshot.adapter';

export interface CollectionObjectSectionItem {
  readonly id: string;
  readonly inventoryNumber: string;
  readonly displayTitle: string | null;
  readonly objectName: string | null;
  readonly briefDescriptionSnapshot: string | null;
  readonly category: string;
  readonly description: string;
  readonly requestedAt?: string;
}

export interface CollectionObjectSelectionRequest {
  readonly objects: readonly ObjectSearchSnapshot[];
}

@Component({
  selector: 'app-collection-objects-section',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ConfirmModalComponent, ErrorMessageComponent],
  templateUrl: './collection-objects-section.component.html',
  styleUrl: './collection-objects-section.component.scss',
})
export class CollectionObjectsSectionComponent {
  private readonly objectSearch = inject(OBJECT_SEARCH_SERVICE);
  private readonly sanitizer = inject(DomSanitizer);

  readonly objects = input.required<readonly CollectionObjectSectionItem[]>();
  readonly title = input('Objects');
  readonly emptyMessage = input('No objects linked.');
  readonly addDialogTitle = input('Add object');
  readonly removeDialogTitle = input('Remove object?');
  readonly removeMessageLead = input('Remove');
  readonly removeMessageScope = input('this item');
  readonly canManage = input(true);
  readonly adding = input(false);
  readonly removingId = input<string | null>(null);
  readonly addError = input<ApiError | null>(null);
  readonly removeError = input<ApiError | null>(null);

  readonly addRequested = output<CollectionObjectSelectionRequest>();
  readonly removeRequested = output<string>();

  protected readonly addModalOpen = signal(false);
  protected readonly removeTargetId = signal<string | null>(null);
  protected readonly searchQuery = signal('');
  protected readonly searchResults = signal<readonly ObjectSearchHit[]>([]);
  protected readonly searchError = signal<ApiError | null>(null);
  protected readonly searching = signal(false);
  protected readonly selectedHitIds = signal<readonly string[]>([]);
  protected readonly removeTargetName = computed(() => {
    const target = this.objects().find((object) => object.id === this.removeTargetId());
    return target ? this.objectLabel(target) : 'this object';
  });

  protected objectLabel(object: CollectionObjectSectionItem): string {
    return object.displayTitle || object.objectName || object.inventoryNumber;
  }

  protected openAddModal(): void {
    if (!this.canManage()) return;
    this.addModalOpen.set(true);
  }

  protected closeAddModal(): void {
    if (this.adding()) return;
    this.addModalOpen.set(false);
  }

  protected onSearchQueryInput(event: Event): void {
    this.searchQuery.set((event.target as HTMLInputElement).value);
  }

  protected async searchObjects(): Promise<void> {
    const q = this.searchQuery().trim();
    if (!q) return;
    this.searching.set(true);
    this.searchError.set(null);
    this.selectedHitIds.set([]);
    try {
      const result = await firstValueFrom(
        this.objectSearch.search({ q, collectionId: undefined, page: 0, size: 20 }),
      );
      this.searchResults.set(result.items);
    } catch (err) {
      this.searchError.set(toApiError(err));
    } finally {
      this.searching.set(false);
    }
  }

  protected hitId(hit: ObjectSearchHit): string {
    return `${hit.sourceDocumentId}:${hit.sheet}:${hit.rowNumber}`;
  }

  protected highlightHtml(hit: ObjectSearchHit): SafeHtml {
    return this.sanitizer.bypassSecurityTrustHtml(highlightToSafeMarkup(hit.highlight));
  }

  protected adapterReason(hit: ObjectSearchHit): string | null {
    const result = adaptSearchHitToObjectSnapshot(hit);
    return result.ok ? null : result.reason;
  }

  protected canAddHit(hit: ObjectSearchHit): boolean {
    return adaptSearchHitToObjectSnapshot(hit).ok;
  }

  protected isHitSelected(hit: ObjectSearchHit): boolean {
    return this.selectedHitIds().includes(this.hitId(hit));
  }

  protected toggleHit(hit: ObjectSearchHit, checked: boolean): void {
    if (!this.canAddHit(hit)) return;
    const id = this.hitId(hit);
    this.selectedHitIds.update((current) => {
      if (checked) return current.includes(id) ? current : [...current, id];
      return current.filter((item) => item !== id);
    });
  }

  protected selectedCount(): number {
    return this.selectedHitIds().length;
  }

  protected selectedItems(): readonly ObjectSearchSnapshot[] {
    const selected = new Set(this.selectedHitIds());
    return this.searchResults().flatMap((hit) => {
      if (!selected.has(this.hitId(hit))) return [];
      const result = adaptSearchHitToObjectSnapshot(hit);
      return result.ok ? [result.item] : [];
    });
  }

  protected submitSelectedObjects(): void {
    const objects = this.selectedItems();
    if (!objects.length || this.adding()) return;
    this.addRequested.emit({ objects });
    this.addModalOpen.set(false);
    this.selectedHitIds.set([]);
  }

  protected requestRemove(objectId: string): void {
    if (!this.canManage() || this.removingId()) return;
    this.removeTargetId.set(objectId);
  }

  protected cancelRemove(): void {
    if (this.removingId()) return;
    this.removeTargetId.set(null);
  }

  protected confirmRemove(): void {
    const targetId = this.removeTargetId();
    if (!targetId || this.removingId()) return;
    this.removeRequested.emit(targetId);
    this.removeTargetId.set(null);
  }
}
