import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  resource,
  signal,
} from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { IDENTITY_SERVICE } from '@core/auth/identity.service';
import { ApiError, getApiErrorPresentation, toApiError } from '@core/http/api-error.model';
import { ConfirmModalComponent } from '@shared/components/confirm-modal/confirm-modal.component';
import { EmptyStateComponent } from '@shared/components/empty-state/empty-state.component';
import { ErrorMessageComponent } from '@shared/components/error-message/error-message.component';
import { FeedbackMessageComponent } from '@shared/components/feedback-message/feedback-message.component';
import { LoadingStateComponent } from '@shared/components/loading-state/loading-state.component';
import { PageHeaderComponent } from '@shared/components/page-header/page-header.component';
import { PaginationComponent } from '@shared/components/pagination/pagination.component';

import {
  KnowledgeExampleDraft,
  KnowledgeExampleModalComponent,
} from '../../components/knowledge-example-modal/knowledge-example-modal.component';
import {
  KnowledgeFilterChange,
  KnowledgeFiltersComponent,
} from '../../components/knowledge-filters/knowledge-filters.component';
import { KnowledgeHistoryComponent } from '../../components/knowledge-history/knowledge-history.component';
import { KnowledgeItemsListComponent } from '../../components/knowledge-items-list/knowledge-items-list.component';
import { KnowledgeSummaryComponent } from '../../components/knowledge-summary/knowledge-summary.component';
import {
  ScientificReturnKnowledgeItem,
  ScientificReturnKnowledgeKind,
  ScientificReturnKnowledgeStatus,
} from '../../../models/scientific-return.model';
import { ScientificReturnApiService } from '../../../services/scientific-return-api.service';

type ConfirmationAction = 'activate' | 'retire';

interface PendingConfirmation {
  readonly action: ConfirmationAction;
  readonly item: ScientificReturnKnowledgeItem;
}

@Component({
  selector: 'app-scientific-return-knowledge-base-page',
  standalone: true,
  imports: [
    ConfirmModalComponent,
    EmptyStateComponent,
    ErrorMessageComponent,
    FeedbackMessageComponent,
    KnowledgeExampleModalComponent,
    KnowledgeFiltersComponent,
    KnowledgeHistoryComponent,
    KnowledgeItemsListComponent,
    KnowledgeSummaryComponent,
    LoadingStateComponent,
    PageHeaderComponent,
    PaginationComponent,
  ],
  templateUrl: './scientific-return-knowledge-base-page.component.html',
  styleUrl: './scientific-return-knowledge-base-page.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ScientificReturnKnowledgeBasePageComponent {
  private readonly api = inject(ScientificReturnApiService);
  private readonly identity = inject(IDENTITY_SERVICE);

  protected readonly status = signal<ScientificReturnKnowledgeStatus | null>(null);
  protected readonly kind = signal<ScientificReturnKnowledgeKind | null>(null);
  protected readonly inventoryNumber = signal<string | null>(null);
  protected readonly page = signal(0);
  protected readonly pageSize = 25;

  protected readonly knowledgeResource = resource({
    params: () => ({
      permissionId: this.identity.getPermissionId(),
      status: this.status(),
      kind: this.kind(),
      inventoryNumber: this.inventoryNumber(),
      page: this.page(),
      size: this.pageSize,
    }),
    loader: ({ params }) => firstValueFrom(this.api.listKnowledgeItems(params)),
  });

  protected readonly result = computed(() =>
    this.knowledgeResource.hasValue() ? this.knowledgeResource.value() : null,
  );
  protected readonly items = computed(() => this.result()?.content ?? []);
  protected readonly counts = computed(
    () => this.result()?.counts ?? { active: 0, proposed: 0, retired: 0 },
  );
  protected readonly loadError = computed<ApiError | null>(() => {
    const error = this.knowledgeResource.error();
    return error ? toApiError(error) : null;
  });
  protected readonly hasFilters = computed(
    () => this.status() !== null || this.kind() !== null || this.inventoryNumber() !== null,
  );
  protected readonly canManage = computed(() => {
    const group = this.identity.session()?.group;
    return group === 'CURATORIAL' || group === 'COLLECTIONS_MANAGEMENT' || group === 'DIRECTION';
  });

  protected readonly busyId = signal<string | null>(null);
  protected readonly actionError = signal<ApiError | null>(null);
  protected readonly feedback = signal<string | null>(null);
  protected readonly editorOpen = signal(false);
  protected readonly editingItem = signal<ScientificReturnKnowledgeItem | null>(null);
  protected readonly confirmation = signal<PendingConfirmation | null>(null);
  protected readonly historyItem = signal<ScientificReturnKnowledgeItem | null>(null);
  protected readonly historyResource = resource({
    params: () => this.historyItem()?.id ?? null,
    loader: ({ params }) =>
      params
        ? firstValueFrom(this.api.getKnowledgeHistory(params))
        : Promise.resolve([] as readonly ScientificReturnKnowledgeItem[]),
  });
  protected readonly historyError = computed(() => {
    const error = this.historyResource.error();
    return error ? getApiErrorPresentation(toApiError(error)).message : null;
  });

  protected applyFilters(change: KnowledgeFilterChange): void {
    this.status.set(change.status);
    this.kind.set(change.kind);
    this.inventoryNumber.set(change.inventoryNumber);
    this.page.set(0);
  }

  protected toggleStatus(status: ScientificReturnKnowledgeStatus): void {
    this.status.update((current) => (current === status ? null : status));
    this.page.set(0);
  }

  protected openCreate(): void {
    this.editingItem.set(null);
    this.editorOpen.set(true);
    this.clearMessages();
  }

  protected openEdit(item: ScientificReturnKnowledgeItem): void {
    this.editingItem.set(item);
    this.editorOpen.set(true);
    this.clearMessages();
  }

  protected closeEditor(): void {
    if (!this.busyId()) this.editorOpen.set(false);
  }

  protected async saveExample(draft: KnowledgeExampleDraft): Promise<void> {
    if (!this.canManage() || this.busyId()) return;
    const item = this.editingItem();
    this.busyId.set(item?.id ?? 'create');
    this.clearMessages();
    try {
      const saved = item
        ? await firstValueFrom(
            this.api.replaceKnowledgeItem(item.id, {
              content: draft.content,
              registeredNumber: draft.registeredNumber || null,
              observedForm: draft.observedForm || null,
            }),
          )
        : await firstValueFrom(this.api.createInventoryExample(draft));
      this.editorOpen.set(false);
      this.editingItem.set(null);
      this.page.set(0);
      this.knowledgeResource.reload();
      this.feedback.set(
        item
          ? `A corrected version (${saved.id}) is now active; the previous version remains in history.`
          : 'The inventory example is active and available to future investigations.',
      );
    } catch (error) {
      this.actionError.set(toApiError(error));
    } finally {
      this.busyId.set(null);
    }
  }

  protected requestConfirmation(
    action: ConfirmationAction,
    item: ScientificReturnKnowledgeItem,
  ): void {
    this.confirmation.set({ action, item });
    this.clearMessages();
  }

  protected async confirmAction(): Promise<void> {
    const pending = this.confirmation();
    if (!pending || !this.canManage() || this.busyId()) return;
    this.busyId.set(pending.item.id);
    try {
      if (pending.action === 'activate') {
        await firstValueFrom(this.api.activateKnowledgeItem(pending.item.id));
        this.feedback.set('The proposed lesson is active and available to future investigations.');
      } else {
        await firstValueFrom(this.api.retireKnowledgeItem(pending.item.id));
        this.feedback.set('The item was retired. It remains available in the audit history.');
      }
      this.confirmation.set(null);
      this.knowledgeResource.reload();
    } catch (error) {
      this.actionError.set(toApiError(error));
    } finally {
      this.busyId.set(null);
    }
  }

  protected showHistory(item: ScientificReturnKnowledgeItem): void {
    this.historyItem.set(item);
  }

  protected previousPage(): void {
    this.page.update((value) => Math.max(0, value - 1));
  }

  protected nextPage(): void {
    const last = Math.max(0, (this.result()?.totalPages ?? 1) - 1);
    this.page.update((value) => Math.min(last, value + 1));
  }

  protected clearMessages(): void {
    this.actionError.set(null);
    this.feedback.set(null);
  }
}
