import {
  ChangeDetectionStrategy,
  Component,
  computed,
  effect,
  inject,
  resource,
  signal,
  untracked,
} from '@angular/core';
import { DatePipe } from '@angular/common';
import { RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { IDENTITY_SERVICE } from '@core/auth/identity.service';
import { ApiError, getApiErrorPresentation, toApiError } from '@core/http/api-error.model';
import { EmptyStateComponent } from '@shared/components/empty-state/empty-state.component';
import { ErrorMessageComponent } from '@shared/components/error-message/error-message.component';
import { LoadingStateComponent } from '@shared/components/loading-state/loading-state.component';
import { PageHeaderComponent } from '@shared/components/page-header/page-header.component';

import { CollectionUseProjectSummary } from '../../models/project.model';
import {
  ScientificReturnWatch,
  ScientificReturnWatchIneligibilityReason,
  ScientificReturnWatchLookupItem,
} from '../../models/scientific-return.model';
import { PROJECT_API_SERVICE } from '../../services/project-api.service';
import { ScientificReturnApiService } from '../../services/scientific-return-api.service';

const DEFAULT_PAGE_SIZE = 20;
const PAGE_SIZE_OPTIONS = [10, 20, 50, 100] as const;
const MAX_BULK_SELECTION = 100;
const BULK_CONCURRENCY = 4;

type BusyAction = 'create' | 'status' | 'configuration' | null;
type WatchFilter = 'ALL' | 'NONE' | 'ACTIVE' | 'PAUSED' | 'CLOSED' | 'INELIGIBLE';

interface WatchRowState {
  readonly watch: ScientificReturnWatch | null;
  readonly eligible: boolean;
  readonly ineligibilityReason: ScientificReturnWatchIneligibilityReason | null;
  readonly anchorDraft: string;
  readonly intervalDraft: string;
  readonly selected: boolean;
  readonly busy: BusyAction;
  readonly error: string | null;
  readonly feedback: string | null;
}

interface LoadedWatchersPage {
  readonly projects: readonly CollectionUseProjectSummary[];
  readonly totalElements: number;
  readonly totalPages: number;
  readonly lookup: readonly ScientificReturnWatchLookupItem[];
}

interface WatcherRow {
  readonly project: CollectionUseProjectSummary;
  readonly state: WatchRowState;
}

const INELIGIBILITY_LABELS: Record<ScientificReturnWatchIneligibilityReason, string> = {
  NO_CONSULTED_OBJECTS: 'The project has no consulted objects.',
  MISSING_INVENTORY_NUMBER: 'A consulted object has no inventory number.',
  MISSING_OBJECT_NAME: 'A consulted object has no object name.',
  REQUESTER_NOT_FOUND: 'The project requester could not be resolved.',
  PROJECT_NOT_COMPLETED: 'The project is not completed.',
};

function todayUtc(): string {
  return new Date().toISOString().slice(0, 10);
}

function stateFromLookup(item: ScientificReturnWatchLookupItem): WatchRowState {
  return {
    watch: item.watch,
    eligible: item.eligible,
    ineligibilityReason: item.ineligibilityReason,
    anchorDraft: item.watch?.scheduleAnchorAt.slice(0, 10) ?? todayUtc(),
    intervalDraft: String(item.watch?.reviewIntervalDays ?? 90),
    selected: false,
    busy: null,
    error: null,
    feedback: null,
  };
}

@Component({
  selector: 'app-project-watchers-page',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    DatePipe,
    RouterLink,
    EmptyStateComponent,
    ErrorMessageComponent,
    LoadingStateComponent,
    PageHeaderComponent,
  ],
  templateUrl: './project-watchers-page.component.html',
  styleUrl: './project-watchers-page.component.scss',
})
export class ProjectWatchersPageComponent {
  private readonly projectsApi = inject(PROJECT_API_SERVICE);
  private readonly watchersApi = inject(ScientificReturnApiService);
  private readonly identity = inject(IDENTITY_SERVICE);

  protected readonly currentPage = signal(0);
  protected readonly pageSize = signal(DEFAULT_PAGE_SIZE);
  protected readonly searchDraft = signal('');
  protected readonly appliedSearch = signal('');
  protected readonly watchFilter = signal<WatchFilter>('ALL');
  protected readonly originProjectId = signal<string | null>(null);
  protected readonly bulkFeedback = signal<string | null>(null);
  protected readonly bulkBusy = signal(false);
  protected readonly maxBulkSelection = MAX_BULK_SELECTION;
  // Deliberately retained across pages so bulk selection survives pagination.
  // The selection cap bounds the amount of actionable retained state.
  private readonly rowStates = signal<ReadonlyMap<string, WatchRowState>>(new Map());
  private previousPermissionId: string | null | undefined;

  protected readonly currentPermissionId = computed(() => this.identity.getPermissionId());
  protected readonly canManage = computed(() => {
    const group = this.identity.session()?.group;
    return group === 'CURATORIAL' || group === 'COLLECTIONS_MANAGEMENT' || group === 'DIRECTION';
  });

  protected readonly watchersResource = resource({
    params: () => ({
      permissionId: this.currentPermissionId(),
      page: this.currentPage(),
      size: this.pageSize(),
      search: this.appliedSearch().trim(),
    }),
    loader: async ({ params }): Promise<LoadedWatchersPage> => {
      const projectsPage = await firstValueFrom(
        this.projectsApi.listProjects({
          status: 'COMPLETED',
          page: params.page,
          size: params.size,
          search: params.search,
        }),
      );
      const lookup = projectsPage.content.length
        ? await firstValueFrom(
            this.watchersApi.lookupWatches(projectsPage.content.map((project) => project.id)),
          )
        : { items: [] };
      return {
        projects: projectsPage.content,
        totalElements: projectsPage.totalElements,
        totalPages: projectsPage.totalPages,
        lookup: lookup.items,
      };
    },
  });

  private readonly synchronizeRows = effect(() => {
    const loaded = this.watchersResource.value();
    if (!loaded) return;
    untracked(() => {
      const lookup = new Map(loaded.lookup.map((item) => [item.projectId, item]));
      this.rowStates.update((current) => {
        const next = new Map(current);
        for (const project of loaded.projects) {
          const item = lookup.get(project.id);
          if (!item) continue;
          const previous = next.get(project.id);
          const fresh = stateFromLookup(item);
          const remainsSelectable =
            fresh.watch?.status !== 'CLOSED' && (fresh.watch !== null || fresh.eligible);
          next.set(
            project.id,
            previous ? { ...fresh, selected: previous.selected && remainsSelectable } : fresh,
          );
        }
        return next;
      });
    });
  });

  private readonly resetSelectionOnIdentityChange = effect(() => {
    const permissionId = this.currentPermissionId();
    if (this.previousPermissionId !== undefined && this.previousPermissionId !== permissionId) {
      untracked(() => this.clearSelection());
    }
    this.previousPermissionId = permissionId;
  });

  protected readonly rows = computed<readonly WatcherRow[]>(() => {
    const loaded = this.watchersResource.value();
    if (!loaded) return [];
    const states = this.rowStates();
    return loaded.projects
      .map((project) => ({ project, state: states.get(project.id) }))
      .filter((row): row is WatcherRow => row.state !== undefined)
      .filter((row) => this.matchesFilter(row.state));
  });
  protected readonly totalProjects = computed(
    () => this.watchersResource.value()?.totalElements ?? 0,
  );
  protected readonly totalPages = computed(() => this.watchersResource.value()?.totalPages ?? 0);
  protected readonly rangeStart = computed(() =>
    this.totalProjects() === 0 ? 0 : this.currentPage() * this.pageSize() + 1,
  );
  protected readonly rangeEnd = computed(() =>
    Math.min((this.currentPage() + 1) * this.pageSize(), this.totalProjects()),
  );
  protected readonly loadError = computed<ApiError | null>(() => {
    const error = this.watchersResource.error();
    return error ? toApiError(error) : null;
  });
  protected readonly selectedCount = computed(
    () => [...this.rowStates().values()].filter((state) => state.selected).length,
  );
  protected readonly pageSizeOptions = PAGE_SIZE_OPTIONS;
  protected readonly ineligibilityLabels = INELIGIBILITY_LABELS;

  private matchesFilter(state: WatchRowState): boolean {
    const filter = this.watchFilter();
    if (filter === 'ALL') return true;
    if (filter === 'INELIGIBLE') return !state.watch && !state.eligible;
    if (filter === 'NONE') return !state.watch && state.eligible;
    return state.watch?.status === filter;
  }

  private updateRow(projectId: string, update: (state: WatchRowState) => WatchRowState): void {
    this.rowStates.update((current) => {
      const state = current.get(projectId);
      if (!state) return current;
      const next = new Map(current);
      next.set(projectId, update(state));
      return next;
    });
  }

  protected requesterLabel(project: CollectionUseProjectSummary): string {
    return project.requestedBy?.user.name ?? 'Unknown requester';
  }

  protected onAnchorInput(projectId: string, event: Event): void {
    const value = (event.target as HTMLInputElement).value;
    this.updateRow(projectId, (state) => ({ ...state, anchorDraft: value, feedback: null }));
  }

  protected onIntervalInput(projectId: string, event: Event): void {
    const value = (event.target as HTMLInputElement).value;
    this.updateRow(projectId, (state) => ({ ...state, intervalDraft: value, feedback: null }));
  }

  protected configurationInvalid(state: WatchRowState): boolean {
    const interval = Number(state.intervalDraft);
    return !state.anchorDraft || !Number.isInteger(interval) || interval < 1 || interval > 365;
  }

  protected async saveConfiguration(projectId: string): Promise<void> {
    const state = this.rowStates().get(projectId);
    if (
      !this.canManage() ||
      !state?.watch ||
      state.watch.status === 'CLOSED' ||
      this.configurationInvalid(state)
    )
      return;
    await this.persistConfiguration(projectId);
  }

  protected async lifecycleAction(projectId: string): Promise<void> {
    const state = this.rowStates().get(projectId);
    if (!state || !this.canManage() || state.busy || this.configurationInvalid(state)) return;
    if (!state.watch) {
      if (!state.eligible) return;
      await this.persistConfiguration(projectId);
      return;
    }
    if (state.watch.status === 'CLOSED') return;
    const status = state.watch.status === 'ACTIVE' ? 'PAUSED' : 'ACTIVE';
    this.updateRow(projectId, (row) => ({ ...row, busy: 'status', error: null, feedback: null }));
    try {
      const watch = await firstValueFrom(
        this.watchersApi.changeWatchStatus(state.watch.id, status),
      );
      this.updateRow(projectId, (row) => ({
        ...row,
        watch,
        busy: null,
        feedback: status === 'ACTIVE' ? 'Watcher started.' : 'All scheduled engines are paused.',
      }));
    } catch (error) {
      this.failRow(projectId, error);
    }
  }

  private async persistConfiguration(projectId: string): Promise<boolean> {
    const state = this.rowStates().get(projectId);
    if (!this.canManage() || !state || state.busy || this.configurationInvalid(state)) return false;
    if (!state.watch && !state.eligible) return false;
    if (state.watch?.status === 'CLOSED') return false;
    this.updateRow(projectId, (row) => ({
      ...row,
      busy: row.watch ? 'configuration' : 'create',
      error: null,
      feedback: null,
    }));
    try {
      const scheduleAnchorAt = new Date(`${state.anchorDraft}T00:00:00Z`).toISOString();
      const reviewIntervalDays = Number(state.intervalDraft);
      const watch = state.watch
        ? await firstValueFrom(
            this.watchersApi.updateWatch(state.watch.id, { scheduleAnchorAt, reviewIntervalDays }),
          )
        : await firstValueFrom(
            this.watchersApi.createWatch(projectId, {
              scheduleAnchorAt,
              reviewIntervalDays,
              startImmediately: false,
            }),
          );
      this.updateRow(projectId, (row) => ({
        ...row,
        watch,
        anchorDraft: watch.scheduleAnchorAt.slice(0, 10),
        intervalDraft: String(watch.reviewIntervalDays),
        busy: null,
        error: null,
        feedback: state.watch ? 'Configuration saved.' : 'Watcher created and paused.',
      }));
      return true;
    } catch (error) {
      this.failRow(projectId, error);
      return false;
    }
  }

  private failRow(projectId: string, error: unknown): void {
    const apiError = toApiError(error);
    this.updateRow(projectId, (row) => ({
      ...row,
      busy: null,
      error: getApiErrorPresentation(apiError).message,
      feedback: null,
    }));
  }

  protected canSelect(state: WatchRowState): boolean {
    return (
      this.canManage() &&
      state.watch?.status !== 'CLOSED' &&
      (state.watch !== null || state.eligible)
    );
  }

  protected toggleSelected(projectId: string, checked: boolean): void {
    const state = this.rowStates().get(projectId);
    if (!state || (checked && !this.canSelect(state))) return;
    if (checked && !state.selected && this.selectedCount() >= MAX_BULK_SELECTION) {
      this.bulkFeedback.set(`You can select at most ${MAX_BULK_SELECTION} projects.`);
      return;
    }
    this.updateRow(projectId, (state) => ({ ...state, selected: checked }));
    this.bulkFeedback.set(null);
  }

  protected onSelectionInput(projectId: string, event: Event): void {
    this.toggleSelected(projectId, (event.target as HTMLInputElement).checked);
  }

  protected setOrigin(projectId: string): void {
    const state = this.rowStates().get(projectId);
    if (!state || !this.canSelect(state) || this.bulkBusy()) return;
    this.originProjectId.set(projectId);
    this.bulkFeedback.set(null);
  }

  protected replicateConfiguration(): void {
    if (!this.canManage() || this.bulkBusy()) return;
    const originId = this.originProjectId();
    const origin = originId ? this.rowStates().get(originId) : null;
    if (!origin) return;
    let copied = 0;
    this.rowStates.update((current) => {
      const next = new Map(current);
      for (const [projectId, state] of current) {
        if (!state.selected || !this.canSelect(state)) continue;
        copied += 1;
        next.set(projectId, {
          ...state,
          anchorDraft: origin.anchorDraft,
          intervalDraft: origin.intervalDraft,
          error: null,
          feedback: 'Configuration copied; apply to persist.',
        });
      }
      return next;
    });
    this.bulkFeedback.set(`Configuration copied to ${copied} selected projects.`);
  }

  protected async applySelected(): Promise<void> {
    if (!this.canManage() || this.bulkBusy()) return;
    const ids = [...this.rowStates()]
      .filter(([, state]) => state.selected && this.canSelect(state))
      .map(([projectId]) => projectId);
    if (!ids.length) {
      this.bulkFeedback.set('No eligible projects are selected.');
      return;
    }
    this.bulkBusy.set(true);
    let successes = 0;
    try {
      for (let index = 0; index < ids.length; index += BULK_CONCURRENCY) {
        const batchIds = ids.slice(index, index + BULK_CONCURRENCY);
        const results = await Promise.all(batchIds.map((id) => this.persistConfiguration(id)));
        results.forEach((succeeded, resultIndex) => {
          if (!succeeded) return;
          successes += 1;
          this.updateRow(batchIds[resultIndex], (state) => ({ ...state, selected: false }));
        });
      }
      this.bulkFeedback.set(`${successes} of ${ids.length} selected projects were applied.`);
    } finally {
      this.bulkBusy.set(false);
    }
  }

  protected onSearchInput(event: Event): void {
    this.searchDraft.set((event.target as HTMLInputElement).value);
  }

  protected applySearch(): void {
    this.currentPage.set(0);
    this.appliedSearch.set(this.searchDraft().trim());
    this.clearSelection();
  }

  protected clearSearch(): void {
    this.searchDraft.set('');
    this.applySearch();
  }

  protected changeFilter(event: Event): void {
    this.watchFilter.set((event.target as HTMLSelectElement).value as WatchFilter);
  }

  protected clearSelection(): void {
    if (this.bulkBusy()) return;
    this.rowStates.update(
      (current) => new Map([...current].map(([id, state]) => [id, { ...state, selected: false }])),
    );
    this.originProjectId.set(null);
    this.bulkFeedback.set(null);
  }

  protected firstPage(): void {
    this.currentPage.set(0);
  }
  protected previousPage(): void {
    this.currentPage.update((page) => Math.max(0, page - 1));
  }
  protected nextPage(): void {
    this.currentPage.update((page) => Math.min(this.totalPages() - 1, page + 1));
  }
  protected lastPage(): void {
    this.currentPage.set(Math.max(0, this.totalPages() - 1));
  }
  protected changePageSize(event: Event): void {
    this.pageSize.set(Number((event.target as HTMLSelectElement).value));
    this.currentPage.set(0);
  }
}
