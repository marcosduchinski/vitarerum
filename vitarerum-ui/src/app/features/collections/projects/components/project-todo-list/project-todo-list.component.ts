import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  input,
  linkedSignal,
  resource,
  signal,
} from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { IDENTITY_SERVICE } from '@core/auth/identity.service';

import { ProjectTodoItem } from '../../models/project.model';
import { PROJECT_API_SERVICE } from '../../services/project-api.service';

@Component({
  selector: 'app-project-todo-list',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './project-todo-list.component.html',
  styleUrl: './project-todo-list.component.scss',
})
export class ProjectTodoListComponent {
  private readonly projectService = inject(PROJECT_API_SERVICE);
  private readonly identity = inject(IDENTITY_SERVICE);

  readonly projectId = input.required<string>();

  protected readonly activePermissionId = computed(() => this.identity.getPermissionId());
  protected readonly draft = linkedSignal(() => {
    this.projectId();
    this.activePermissionId();
    return '';
  });
  protected readonly todoResource = resource({
    params: () => ({
      projectId: this.projectId(),
      permissionId: this.activePermissionId(),
    }),
    loader: ({ params }) => {
      if (!params.permissionId) return Promise.resolve({ projectId: params.projectId, items: [] });
      return firstValueFrom(this.projectService.listTodoItems(params.projectId));
    },
  });
  protected readonly items = computed<readonly ProjectTodoItem[]>(
    () => this.todoResource.value()?.items ?? [],
  );
  protected readonly completedCount = computed(
    () => this.items().filter((item) => item.completed).length,
  );
  protected readonly error = signal<string | null>(null);
  protected readonly adding = signal(false);
  protected readonly busyItemId = signal<string | null>(null);

  protected onDraftInput(event: Event): void {
    this.draft.set((event.target as HTMLInputElement).value);
    this.error.set(null);
  }

  protected async addItem(event: SubmitEvent): Promise<void> {
    event.preventDefault();
    const text = this.draft().trim();
    if (!text || this.adding()) return;

    this.adding.set(true);
    this.error.set(null);
    try {
      const item = await firstValueFrom(
        this.projectService.createTodoItem(this.projectId(), { text }),
      );
      this.draft.set('');
      this.todoResource.set({ projectId: this.projectId(), items: [...this.items(), item] });
    } catch {
      this.error.set('Could not save the item.');
    } finally {
      this.adding.set(false);
    }
  }

  protected async setCompleted(item: ProjectTodoItem, event: Event): Promise<void> {
    const completed = (event.target as HTMLInputElement).checked;
    if (this.busyItemId() === item.id) return;

    this.busyItemId.set(item.id);
    this.error.set(null);
    try {
      let updated: ProjectTodoItem;
      if (completed) {
        updated = await firstValueFrom(
          this.projectService.completeTodoItem(this.projectId(), item.id),
        );
      } else {
        updated = await firstValueFrom(
          this.projectService.reopenTodoItem(this.projectId(), item.id),
        );
      }
      this.todoResource.set({
        projectId: this.projectId(),
        items: this.items().map((candidate) => (candidate.id === item.id ? updated : candidate)),
      });
    } catch {
      (event.target as HTMLInputElement).checked = item.completed;
      this.error.set('Could not update the item.');
    } finally {
      this.busyItemId.set(null);
    }
  }

  protected async removeItem(item: ProjectTodoItem): Promise<void> {
    if (this.busyItemId() === item.id) return;

    this.busyItemId.set(item.id);
    this.error.set(null);
    try {
      await firstValueFrom(this.projectService.deleteTodoItem(this.projectId(), item.id));
      this.todoResource.set({
        projectId: this.projectId(),
        items: this.items().filter((candidate) => candidate.id !== item.id),
      });
    } catch {
      this.error.set('Could not remove the item.');
    } finally {
      this.busyItemId.set(null);
    }
  }
}
