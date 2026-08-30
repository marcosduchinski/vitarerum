import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  resource,
  signal,
} from '@angular/core';
import { RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { GroupName } from '@core/auth/models/group-name.enum';
import { IDENTITY_SERVICE } from '@core/auth/identity.service';
import {
  ProjectTodoPostit,
  ProjectTodoPostitsResponse,
} from '@features/collections/projects/models/project.model';
import { PROJECT_API_SERVICE } from '@features/collections/projects/services/project-api.service';

const WIDGET_SIZE = 20;
const EMPTY_POSTIT_PAGE: ProjectTodoPostitsResponse = {
  content: [],
  page: 0,
  size: WIDGET_SIZE,
  totalElements: 0,
  totalPages: 0,
};

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [RouterLink],
  templateUrl: './dashboard.component.html',
  styleUrl: './dashboard.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class DashboardComponent {
  private readonly projectService = inject(PROJECT_API_SERVICE);
  private readonly identity = inject(IDENTITY_SERVICE);

  protected readonly error = signal<string | null>(null);
  protected readonly busyPostitId = signal<string | null>(null);
  protected readonly session = computed(() => this.identity.session());
  protected readonly activeGroup = computed(() => this.session()?.group ?? null);
  protected readonly activePermissionId = computed(() => this.identity.getPermissionId());
  protected readonly postitsResource = resource({
    params: () => ({
      group: this.activeGroup(),
      permissionId: this.activePermissionId(),
    }),
    loader: ({ params }) => {
      if (!params.group || !params.permissionId || !this.identity.isStaff()) {
        return Promise.resolve(EMPTY_POSTIT_PAGE);
      }
      return firstValueFrom(
        this.projectService.listMyTodoPostits({ completed: false, page: 0, size: WIDGET_SIZE }),
      );
    },
  });
  protected readonly postits = computed<readonly ProjectTodoPostit[]>(
    () => this.postitsResource.value()?.content ?? [],
  );
  /** How many the widget could not show; the full list lives on the TODO page. */
  protected readonly hiddenPostitCount = computed(() =>
    Math.max(0, (this.postitsResource.value()?.totalElements ?? 0) - this.postits().length),
  );

  /** A post-it links back to the tab it came from, not the project's default one. */
  protected readonly todoTabQueryParams = { tab: 'todo' } as const;

  protected projectDetailRoute(projectId: string): readonly string[] {
    const group = this.activeGroup();
    if (group === 'CURATORIAL') return ['/p/collections/projects/curatorial', projectId];
    if (group === 'DIRECTION') return ['/p/collections/projects/direction', projectId];
    if (group === 'COLLECTIONS_MANAGEMENT' || group === 'SYS_ADMIN') {
      return ['/p/collections/projects/collections', projectId];
    }
    return ['/p/collections/projects', projectId];
  }

  protected formatUpdatedAt(value: string): string {
    return new Intl.DateTimeFormat('en-GB', {
      day: '2-digit',
      month: 'short',
    }).format(new Date(value));
  }

  protected async completePostit(item: ProjectTodoPostit): Promise<void> {
    if (this.busyPostitId() === item.id) return;
    this.busyPostitId.set(item.id);
    this.error.set(null);
    try {
      await firstValueFrom(this.projectService.completeTodoItem(item.projectId, item.id));
      const current = this.postitsResource.value() ?? EMPTY_POSTIT_PAGE;
      const remaining = this.postits().filter((candidate) => candidate.id !== item.id);
      this.postitsResource.set({
        ...current,
        content: remaining,
        totalElements: Math.max(0, current.totalElements - 1),
      });
    } catch {
      this.error.set('Could not complete the TODO item.');
    } finally {
      this.busyPostitId.set(null);
    }
  }

  protected groupLabel(group: GroupName | null): string {
    switch (group) {
      case 'CURATORIAL':
        return 'Curatorial';
      case 'COLLECTIONS_MANAGEMENT':
        return 'Collections management';
      case 'DIRECTION':
        return 'Direction';
      case 'SYS_ADMIN':
        return 'System administration';
      default:
        return 'Workspace';
    }
  }
}
