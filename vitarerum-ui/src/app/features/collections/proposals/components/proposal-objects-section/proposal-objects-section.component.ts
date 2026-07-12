import { ChangeDetectionStrategy, Component, inject, input, output, signal } from '@angular/core';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';
import { firstValueFrom } from 'rxjs';

import { ApiError, toApiError } from '@core/http/api-error.model';
import { ObjectSearchHit } from '@features/objects/models/object-search.model';
import { OBJECT_SEARCH_SERVICE } from '@features/objects/services/object-search.service';
import { ConfirmModalComponent } from '@shared/components/confirm-modal/confirm-modal.component';
import { ErrorMessageComponent } from '@shared/components/error-message/error-message.component';
import { highlightToSafeMarkup } from '@shared/utils/highlight-html.util';

import { adaptSearchHitToRequestedObject } from '../../adapters/requested-object-search.adapter';
import { AddRequestedObjectsRequest } from '../../models/proposal-actions.model';
import { RequestedObject } from '../../models/proposal.model';
import { formatProposalDetailDateTime } from '../../proposal-detail.presentation';

@Component({
  selector: 'app-proposal-objects-section',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ConfirmModalComponent, ErrorMessageComponent],
  templateUrl: './proposal-objects-section.component.html',
  styleUrl: './proposal-objects-section.component.scss',
})
export class ProposalObjectsSectionComponent {
  private readonly objectSearch = inject(OBJECT_SEARCH_SERVICE);
  private readonly sanitizer = inject(DomSanitizer);

  readonly objects = input.required<readonly RequestedObject[]>();
  readonly removingId = input<string | null>(null);
  readonly removeError = input<ApiError | null>(null);
  readonly addError = input<ApiError | null>(null);
  readonly adding = input(false);

  readonly removeRequested = output<string>();
  readonly addRequested = output<AddRequestedObjectsRequest>();

  protected readonly addModalOpen = signal(false);
  protected readonly removeTargetId = signal<string | null>(null);
  protected readonly searchQuery = signal('');
  protected readonly searchResults = signal<readonly ObjectSearchHit[]>([]);
  protected readonly searchError = signal<ApiError | null>(null);
  protected readonly searching = signal(false);
  protected readonly selectedHitIds = signal<readonly string[]>([]);

  protected formatDate(value: string): string {
    return formatProposalDetailDateTime(value);
  }

  protected readonly removeTargetName = () => {
    const targetId = this.removeTargetId();
    const target = this.objects().find((object) => object.id === targetId);
    return (
      target?.objectReference.displayTitle ??
      target?.objectReference.objectName ??
      target?.objectReference.inventoryNumber ??
      'this object'
    );
  };

  protected openAddModal(): void {
    this.addModalOpen.set(true);
  }

  protected closeAddModal(): void {
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
    // Safe: highlightToSafeMarkup() escapes the whole string and only re-opens
    // <mark> for the backend's own <b> markers — never trust hit.highlight raw.
    return this.sanitizer.bypassSecurityTrustHtml(highlightToSafeMarkup(hit.highlight));
  }

  protected selectedCount(): number {
    return this.selectedHitIds().length;
  }

  protected adapterReason(hit: ObjectSearchHit): string | null {
    const result = adaptSearchHitToRequestedObject(hit);
    return result.ok ? null : result.reason;
  }

  protected canAddHit(hit: ObjectSearchHit): boolean {
    return adaptSearchHitToRequestedObject(hit).ok;
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

  protected selectedItems(): AddRequestedObjectsRequest['objects'] {
    const selected = new Set(this.selectedHitIds());
    return this.searchResults().flatMap((hit) => {
      if (!selected.has(this.hitId(hit))) return [];
      const result = adaptSearchHitToRequestedObject(hit);
      return result.ok ? [result.item] : [];
    });
  }

  protected submitSelectedObjects(): void {
    const objects = this.selectedItems();
    if (objects.length === 0 || this.adding()) return;
    this.addRequested.emit({ objects });
    this.addModalOpen.set(false);
    this.selectedHitIds.set([]);
  }

  protected requestRemove(objectId: string): void {
    if (this.removingId()) return;
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
