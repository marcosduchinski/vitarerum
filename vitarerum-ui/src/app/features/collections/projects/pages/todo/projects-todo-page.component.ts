import {
  ChangeDetectionStrategy,
  Component,
  computed,
  effect,
  inject,
  linkedSignal,
  resource,
  signal,
} from '@angular/core';
import { RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { IDENTITY_SERVICE } from '@core/auth/identity.service';
import { ApiError, toApiError } from '@core/http/api-error.model';
import { EmptyStateComponent } from '@shared/components/empty-state/empty-state.component';
import { ErrorMessageComponent } from '@shared/components/error-message/error-message.component';
import { LoadingStateComponent } from '@shared/components/loading-state/loading-state.component';
import { PageHeaderComponent } from '@shared/components/page-header/page-header.component';
import { PaginationComponent } from '@shared/components/pagination/pagination.component';
import { StatusChipComponent } from '@shared/components/status-chip/status-chip.component';

import { ProjectPickerComponent } from '../../components/project-picker/project-picker.component';
import {
  CollectionUseProjectSummary,
  ProjectTodoPostit,
  ProjectTodoPostitsResponse,
} from '../../models/project.model';
import { PROJECT_API_SERVICE } from '../../services/project-api.service';
import { projectDetailRouteForGroup } from '../../utils/project-detail-route.util';

const PAGE_SIZE = 20;
const MAX_TEXT_LENGTH = 160;

type TodoFilter = 'open' | 'completed' | 'all';

const EMPTY_PAGE: ProjectTodoPostitsResponse = {
  content: [],
  page: 0,
  size: PAGE_SIZE,
  totalElements: 0,
  totalPages: 0,
};

/** One project's slice of the flat page the server returned. Groups never
 *  straddle a page boundary because the server orders by project first. */
interface TodoGroup {
  readonly projectId: string;
  readonly referenceNumber: string;
  readonly title: string;
  readonly status: CollectionUseProjectSummary['status'];
  readonly items: readonly ProjectTodoPostit[];
}

@Component({
  selector: 'app-projects-todo-page',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    RouterLink,
    PageHeaderComponent,
    PaginationComponent,
    LoadingStateComponent,
    ErrorMessageComponent,
    EmptyStateComponent,
    StatusChipComponent,
    ProjectPickerComponent,
  ],
  templateUrl: './projects-todo-page.component.html',
  styleUrl: './projects-todo-page.component.scss',
})
export class ProjectsTodoPageComponent {
  private readonly projectService = inject(PROJECT_API_SERVICE);
  private readonly identity = inject(IDENTITY_SERVICE);

  protected readonly pageSize = PAGE_SIZE;
  protected readonly maxTextLength = MAX_TEXT_LENGTH;

  // TODO items belong to the acting permission, not the user: switching profile
  // switches the whole list, so every query is keyed on it.
  protected readonly activePermissionId = computed(() => this.identity.getPermissionId());

  protected readonly filter = signal<TodoFilter>('open');
  protected readonly currentPage = signal(0);
  /** The project the composer writes to, and — when set — the list filter. */
  protected readonly selectedProject = signal<CollectionUseProjectSummary | null>(null);
  protected readonly filterBySelectedProject = signal(false);

  protected readonly draft = linkedSignal(() => {
    this.activePermissionId();
    return '';
  });
  protected readonly draftRemaining = computed(() => MAX_TEXT_LENGTH - this.draft().length);

  protected readonly adding = signal(false);
  protected readonly busyItemId = signal<string | null>(null);
  protected readonly actionError = signal<string | null>(null);

  private readonly projectFilterId = computed(() =>
    this.filterBySelectedProject() ? (this.selectedProject()?.id ?? null) : null,
  );

  protected readonly todosResource = resource({
    params: () => ({
      permissionId: this.activePermissionId(),
      filter: this.filter(),
      projectId: this.projectFilterId(),
      page: this.currentPage(),
    }),
    loader: ({ params }) => {
      if (!params.permissionId) return Promise.resolve(EMPTY_PAGE);
      return firstValueFrom(
        this.projectService.listMyTodoPostits({
          completed: params.filter === 'all' ? undefined : params.filter === 'completed',
          projectId: params.projectId ?? undefined,
          sort: 'project',
          page: params.page,
          size: PAGE_SIZE,
        }),
      );
    },
  });

  protected readonly items = computed<readonly ProjectTodoPostit[]>(
    () => this.todosResource.value()?.content ?? [],
  );
  protected readonly total = computed(() => this.todosResource.value()?.totalElements ?? 0);
  protected readonly totalPages = computed(() => this.todosResource.value()?.totalPages ?? 0);
  protected readonly loadError = computed<ApiError | null>(() => {
    const err = this.todosResource.error();
    return err ? toApiError(err) : null;
  });

  constructor() {
    // Deleting or completing the last item on a page leaves the current index
    // past the end; step back instead of showing an empty list.
    effect(() => {
      const pages = this.totalPages();
      if (pages > 0 && this.currentPage() > pages - 1) {
        this.currentPage.set(pages - 1);
      }
    });
  }

  protected readonly groups = computed<readonly TodoGroup[]>(() => {
    const groups: TodoGroup[] = [];
    for (const item of this.items()) {
      const last = groups.at(-1);
      if (last?.projectId === item.projectId) {
        (last.items as ProjectTodoPostit[]).push(item);
        continue;
      }
      groups.push({
        projectId: item.projectId,
        referenceNumber: item.projectReferenceNumber,
        title: item.projectTitle,
        status: item.projectStatus,
        items: [item],
      });
    }
    return groups;
  });

  protected readonly canAdd = computed(
    () => !!this.selectedProject() && !!this.draft().trim() && !this.adding(),
  );

  protected todoTabRoute(projectId: string): readonly string[] {
    return projectDetailRouteForGroup(projectId, this.identity.session()?.group);
  }

  protected readonly todoTabQueryParams = { tab: 'todo' } as const;

  protected onProjectSelected(project: CollectionUseProjectSummary | null): void {
    this.selectedProject.set(project);
    this.actionError.set(null);
    if (!project) {
      this.filterBySelectedProject.set(false);
      this.currentPage.set(0);
    }
  }

  protected onDraftInput(event: Event): void {
    this.draft.set((event.target as HTMLInputElement).value);
    this.actionError.set(null);
  }

  protected selectFilter(filter: TodoFilter): void {
    if (this.filter() === filter) return;
    this.filter.set(filter);
    this.currentPage.set(0);
  }

  protected toggleProjectFilter(event: Event): void {
    this.filterBySelectedProject.set((event.target as HTMLInputElement).checked);
    this.currentPage.set(0);
  }

  protected previousPage(): void {
    this.currentPage.update((page) => Math.max(0, page - 1));
  }

  protected nextPage(): void {
    this.currentPage.update((page) => Math.min(page + 1, Math.max(0, this.totalPages() - 1)));
  }

  protected async addItem(event: SubmitEvent): Promise<void> {
    event.preventDefault();
    const project = this.selectedProject();
    const text = this.draft().trim();
    if (!project || !text || this.adding()) return;

    this.adding.set(true);
    this.actionError.set(null);
    try {
      await firstValueFrom(this.projectService.createTodoItem(project.id, { text }));
      this.draft.set('');
      // A new item lands wherever the current sort and page put it, so reload
      // rather than splicing it into a page it may not belong on.
      this.todosResource.reload();
    } catch {
      this.actionError.set('Could not save the item.');
    } finally {
      this.adding.set(false);
    }
  }

  protected async setCompleted(item: ProjectTodoPostit, event: Event): Promise<void> {
    const completed = (event.target as HTMLInputElement).checked;
    if (this.busyItemId() === item.id) return;

    this.busyItemId.set(item.id);
    this.actionError.set(null);
    try {
      if (completed) {
        await firstValueFrom(this.projectService.completeTodoItem(item.projectId, item.id));
      } else {
        await firstValueFrom(this.projectService.reopenTodoItem(item.projectId, item.id));
      }
      // Toggling can move the item out of the active filter, so the page has to
      // come back from the server rather than be patched in place.
      this.todosResource.reload();
    } catch {
      (event.target as HTMLInputElement).checked = item.completed;
      this.actionError.set('Could not update the item.');
    } finally {
      this.busyItemId.set(null);
    }
  }

  protected async removeItem(item: ProjectTodoPostit): Promise<void> {
    if (this.busyItemId() === item.id) return;

    this.busyItemId.set(item.id);
    this.actionError.set(null);
    try {
      await firstValueFrom(this.projectService.deleteTodoItem(item.projectId, item.id));
      this.todosResource.reload();
    } catch {
      this.actionError.set('Could not remove the item.');
    } finally {
      this.busyItemId.set(null);
    }
  }
}
