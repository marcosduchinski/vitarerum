import { ChangeDetectionStrategy, Component, computed, input, linkedSignal } from '@angular/core';

interface ProjectTodoItem {
  readonly id: number;
  readonly text: string;
  readonly completed: boolean;
}

@Component({
  selector: 'app-project-todo-list',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './project-todo-list.component.html',
  styleUrl: './project-todo-list.component.scss',
})
export class ProjectTodoListComponent {
  readonly projectId = input.required<string>();

  protected readonly draft = linkedSignal(() => {
    this.projectId();
    return '';
  });
  protected readonly items = linkedSignal<readonly ProjectTodoItem[]>(() => {
    this.projectId();
    return [];
  });
  protected readonly completedCount = computed(
    () => this.items().filter((item) => item.completed).length,
  );

  private nextItemId = 1;

  protected onDraftInput(event: Event): void {
    this.draft.set((event.target as HTMLInputElement).value);
  }

  protected addItem(event: SubmitEvent): void {
    event.preventDefault();
    const text = this.draft().trim();
    if (!text) return;

    this.items.update((items) => [...items, { id: this.nextItemId++, text, completed: false }]);
    this.draft.set('');
  }

  protected setCompleted(itemId: number, event: Event): void {
    const completed = (event.target as HTMLInputElement).checked;
    this.items.update((items) =>
      items.map((item) => (item.id === itemId ? { ...item, completed } : item)),
    );
  }

  protected removeItem(itemId: number): void {
    this.items.update((items) => items.filter((item) => item.id !== itemId));
  }
}
