import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  input,
  model,
  resource,
  signal,
} from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { ApiError, toApiError } from '@core/http/api-error.model';
import { UseStatus, getUseStatusPresentation } from '@shared/models/collection-use-status.model';

import { CollectionUseProjectSummary } from '../../models/project.model';
import { PROJECT_API_SERVICE } from '../../services/project-api.service';

/** Every project is offered, whatever its status — a completed or cancelled
 *  project can still gain a follow-up. Each result carries its status so the
 *  choice is informed rather than blind. */
const RESULT_LIMIT = 20;

@Component({
  selector: 'app-project-picker',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './project-picker.component.html',
  styleUrl: './project-picker.component.scss',
})
export class ProjectPickerComponent {
  private readonly projectService = inject(PROJECT_API_SERVICE);

  readonly label = input('Project');
  readonly selected = model<CollectionUseProjectSummary | null>(null);
  readonly disabled = input(false);
  readonly clearLabel = input<string>();

  protected readonly draft = signal('');
  protected readonly appliedSearch = signal<string | null>(null);
  protected readonly open = signal(false);

  protected readonly resultsResource = resource({
    params: () => ({ search: this.appliedSearch() }),
    loader: ({ params }) => {
      if (params.search === null) return Promise.resolve([]);
      return firstValueFrom(
        this.projectService.listProjects({
          search: params.search || undefined,
          page: 0,
          size: RESULT_LIMIT,
        }),
      ).then((page) =>
        [...page.content].sort((a, b) => a.referenceNumber.localeCompare(b.referenceNumber)),
      );
    },
  });

  protected readonly results = computed<readonly CollectionUseProjectSummary[]>(
    () => this.resultsResource.value() ?? [],
  );
  protected readonly searchError = computed<ApiError | null>(() => {
    const err = this.resultsResource.error();
    return err ? toApiError(err) : null;
  });
  protected readonly searched = computed(() => this.appliedSearch() !== null);
  /** The visible title is ellipsised when it does not fit, so the full text has
   *  to stay reachable through the accessible name and the tooltip. */
  protected readonly triggerLabel = computed(() => {
    const project = this.selected();
    return project
      ? `${this.label()}: ${project.referenceNumber} — ${project.title}`
      : `${this.label()}: none chosen`;
  });

  protected statusLabel(status: UseStatus): string {
    return getUseStatusPresentation(status).label;
  }

  protected onDraftInput(event: Event): void {
    this.draft.set((event.target as HTMLInputElement).value);
  }

  protected search(event: Event): void {
    event.preventDefault();
    if (this.disabled()) return;
    this.open.set(true);
    this.appliedSearch.set(this.draft().trim());
  }

  protected close(): void {
    this.open.set(false);
  }

  protected choose(project: CollectionUseProjectSummary): void {
    this.selected.set(project);
    this.open.set(false);
    this.draft.set('');
    this.appliedSearch.set(null);
  }

  protected clear(): void {
    this.selected.set(null);
  }

  protected toggle(): void {
    if (this.disabled()) return;
    this.open.update((value) => !value);
  }
}
