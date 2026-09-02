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
import {
  FiltersBarComponent,
  FiltersBarSelect,
  FiltersBarSelectChange,
} from '@shared/components/filters-bar/filters-bar.component';
import { LoadingStateComponent } from '@shared/components/loading-state/loading-state.component';
import { PageHeaderComponent } from '@shared/components/page-header/page-header.component';
import { PaginationComponent } from '@shared/components/pagination/pagination.component';

import {
  KnowledgeExampleDraft,
  KnowledgeExampleModalComponent,
} from '../../components/knowledge-example-modal/knowledge-example-modal.component';
import { KnowledgeHistoryComponent } from '../../components/knowledge-history/knowledge-history.component';
import { KnowledgeItemsListComponent } from '../../components/knowledge-items-list/knowledge-items-list.component';
import {
  ScientificReturnKnowledgeItem,
  ScientificReturnKnowledgeKind,
  ScientificReturnKnowledgeStatus,
} from '../../../models/scientific-return.model';
import { ScientificReturnApiService } from '../../../services/scientific-return-api.service';

type ConfirmationAction = 'activate' | 'reject' | 'retire';

interface PendingConfirmation {
  readonly action: ConfirmationAction;
  readonly item: ScientificReturnKnowledgeItem;
}

interface ConfirmationCopy {
  readonly title: string;
  readonly message: string;
  readonly confirmLabel: string;
  readonly tone: 'default' | 'danger';
}

const CONFIRMATION_COPY: Record<ConfirmationAction, ConfirmationCopy> = {
  activate: {
    title: 'Validate and activate?',
    message: 'A human validation makes this lesson available to future autonomous investigations.',
    confirmLabel: 'Validate and activate',
    tone: 'default',
  },
  reject: {
    title: 'Discard this proposal?',
    message:
      'The agent proposal is turned down and never reaches an investigation. It stays in the audit history, recorded against your name.',
    confirmLabel: 'Discard proposal',
    tone: 'danger',
  },
  retire: {
    title: 'Retire this knowledge item?',
    message:
      'It will stop influencing future investigations, but remains available in its audit history.',
    confirmLabel: 'Retire item',
    tone: 'danger',
  },
};

@Component({
  selector: 'app-scientific-return-knowledge-base-page',
  standalone: true,
  imports: [
    ConfirmModalComponent,
    EmptyStateComponent,
    ErrorMessageComponent,
    FeedbackMessageComponent,
    FiltersBarComponent,
    KnowledgeExampleModalComponent,
    KnowledgeHistoryComponent,
    KnowledgeItemsListComponent,
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
  protected readonly search = signal<string | null>(null);
  protected readonly page = signal(0);
  protected readonly pageSize = 25;

  protected readonly knowledgeResource = resource({
    params: () => ({
      permissionId: this.identity.getPermissionId(),
      status: this.status(),
      kind: this.kind(),
      q: this.search(),
      page: this.page(),
      size: this.pageSize,
    }),
    loader: ({ params }) => firstValueFrom(this.api.listKnowledgeItems(params)),
  });

  protected readonly result = computed(() =>
    this.knowledgeResource.hasValue() ? this.knowledgeResource.value() : null,
  );
  protected readonly items = computed(() => this.result()?.content ?? []);
  protected readonly loadError = computed<ApiError | null>(() => {
    const error = this.knowledgeResource.error();
    return error ? toApiError(error) : null;
  });
  protected readonly hasFilters = computed(
    () => this.status() !== null || this.kind() !== null || this.search() !== null,
  );
  protected readonly filterSelects = computed<readonly FiltersBarSelect[]>(() => [
    {
      key: 'status',
      label: 'Status',
      value: this.status() ?? '',
      options: [
        { value: '', label: 'All statuses' },
        { value: 'ACTIVE', label: 'Active' },
        { value: 'PROPOSED', label: 'Awaiting validation' },
        { value: 'RETIRED', label: 'Retired or discarded' },
      ],
    },
    {
      key: 'kind',
      label: 'Type',
      value: this.kind() ?? '',
      options: [
        { value: '', label: 'All types' },
        { value: 'INVENTORY_VARIATION_EXAMPLE', label: 'Inventory example' },
        { value: 'CURATORIAL_LESSON', label: 'Curatorial lesson' },
      ],
    },
  ]);
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
  protected readonly confirmationCopy = computed(() => {
    const pending = this.confirmation();
    return pending ? CONFIRMATION_COPY[pending.action] : null;
  });
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

  protected applyFilter(change: FiltersBarSelectChange): void {
    if (change.key === 'status') {
      this.status.set((change.value || null) as ScientificReturnKnowledgeStatus | null);
    } else {
      this.kind.set((change.value || null) as ScientificReturnKnowledgeKind | null);
    }
    this.page.set(0);
  }

  protected applySearch(term: string | null): void {
    this.search.set(term);
    this.page.set(0);
  }

  protected clearFilters(): void {
    this.status.set(null);
    this.kind.set(null);
    this.search.set(null);
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
      } else if (pending.action === 'reject') {
        await firstValueFrom(this.api.retireKnowledgeItem(pending.item.id));
        this.feedback.set(
          'The proposal was discarded. It never reached an investigation and stays in the audit history.',
        );
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
