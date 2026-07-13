import {
  ChangeDetectionStrategy,
  Component,
  computed,
  effect,
  inject,
  input,
  resource,
  signal,
} from '@angular/core';
import { FormField, form, validate } from '@angular/forms/signals';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { ApiError, toApiError } from '@core/http/api-error.model';
import { ErrorMessageComponent } from '@shared/components/error-message/error-message.component';
import { LoadingStateComponent } from '@shared/components/loading-state/loading-state.component';
import {
  StatusChipComponent,
  WorkflowStatus,
} from '@shared/components/status-chip/status-chip.component';

import { CollectionUseProjectDetail, UpdateProjectRequest } from '../../models/project.model';
import { PROJECT_API_SERVICE } from '../../services/project-api.service';

interface ProjectEditFormModel {
  readonly title: string;
  readonly purpose: string;
  readonly beginDate: string;
  readonly endDate: string;
}

interface ProjectEditSnapshot {
  readonly title: string;
  readonly purpose: string;
  readonly beginDate: string;
  readonly endDate: string;
}

const EMPTY_FORM: ProjectEditFormModel = {
  title: '',
  purpose: '',
  beginDate: '',
  endDate: '',
};

@Component({
  selector: 'app-project-edit-page',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    RouterLink,
    FormField,
    LoadingStateComponent,
    ErrorMessageComponent,
    StatusChipComponent,
  ],
  templateUrl: './project-edit-page.component.html',
  styleUrl: './project-edit-page.component.scss',
})
export class ProjectEditPageComponent {
  private readonly projectService = inject(PROJECT_API_SERVICE);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);
  private loadedProjectId: string | null = null;

  readonly id = input.required<string>();

  protected readonly projectResource = resource({
    params: () => this.id(),
    loader: ({ params }) => firstValueFrom(this.projectService.getProject(params)),
  });
  protected readonly project = computed(() => this.projectResource.value() ?? null);
  protected readonly loadError = computed<ApiError | null>(() => {
    const error = this.projectResource.error();
    return error ? toApiError(error) : null;
  });
  protected readonly pending = signal(false);
  protected readonly updateError = signal<ApiError | null>(null);
  protected readonly formModel = signal<ProjectEditFormModel>({ ...EMPTY_FORM });
  protected readonly original = signal<ProjectEditSnapshot | null>(null);
  protected readonly detailLink = computed(() => [
    '/p/collections/projects',
    this.route.snapshot.routeConfig?.path?.split('/')[0] ?? 'collections',
    this.id(),
  ]);

  protected readonly editForm = form(this.formModel, (path) => {
    validate(path.title, ({ value }) =>
      value().trim() ? undefined : { kind: 'required', message: 'Title is required.' },
    );
    validate(path.purpose, ({ value }) =>
      value().trim() ? undefined : { kind: 'required', message: 'Purpose is required.' },
    );
    validate(path.endDate, ({ value, valueOf }) => {
      const beginDate = valueOf(path.beginDate);
      const endDate = value();
      return beginDate && endDate && endDate < beginDate
        ? { kind: 'date-range', message: 'End date cannot precede begin date.' }
        : undefined;
    });
  });

  protected readonly canEdit = computed(() => {
    const status = this.project()?.status;
    return status === 'CREATED' || status === 'IN_PROGRESS';
  });
  protected readonly changed = computed(() => {
    const original = this.original();
    return original ? !this.snapshotsEqual(original, this.currentSnapshot()) : false;
  });
  protected readonly saveDisabled = computed(
    () =>
      this.pending() ||
      !this.project() ||
      !this.canEdit() ||
      !this.changed() ||
      this.editForm().invalid(),
  );

  private readonly syncForm = effect(() => {
    const project = this.project();
    if (!project || this.loadedProjectId === project.id) return;

    this.loadedProjectId = project.id;
    const snapshot = this.snapshotFromProject(project);
    this.original.set(snapshot);
    this.formModel.set({ ...snapshot });
    this.updateError.set(null);
  });

  protected asWorkflowStatus(value: string): WorkflowStatus {
    return value as WorkflowStatus;
  }

  protected async save(event: Event): Promise<void> {
    event.preventDefault();
    this.editForm().markAsTouched();
    if (this.saveDisabled()) return;

    const request = this.buildRequest();
    if (!Object.keys(request).length) return;

    this.pending.set(true);
    this.updateError.set(null);
    try {
      await firstValueFrom(this.projectService.updateProject(this.id(), request));
      await this.navigateToDetail();
    } catch (error) {
      this.updateError.set(toApiError(error));
    } finally {
      this.pending.set(false);
    }
  }

  protected cancel(): void {
    if (this.pending()) return;
    void this.navigateToDetail();
  }

  private buildRequest(): UpdateProjectRequest {
    const original = this.original();
    if (!original) return {};
    const current = this.currentSnapshot();
    const request: {
      title?: string | null;
      purpose?: string | null;
      beginDate?: string | null;
      endDate?: string | null;
    } = {};
    if (current.title !== original.title) request.title = current.title;
    if (current.purpose !== original.purpose) request.purpose = current.purpose;
    if (current.beginDate !== original.beginDate) request.beginDate = current.beginDate;
    if (current.endDate !== original.endDate) request.endDate = current.endDate;
    return request;
  }

  private currentSnapshot(): ProjectEditSnapshot {
    const value = this.formModel();
    return {
      title: value.title.trim(),
      purpose: value.purpose.trim(),
      beginDate: value.beginDate,
      endDate: value.endDate,
    };
  }

  private snapshotFromProject(project: CollectionUseProjectDetail): ProjectEditSnapshot {
    return {
      title: project.title.trim(),
      purpose: project.purpose.trim(),
      beginDate: project.beginDate,
      endDate: project.endDate,
    };
  }

  private snapshotsEqual(a: ProjectEditSnapshot, b: ProjectEditSnapshot): boolean {
    return (
      a.title === b.title &&
      a.purpose === b.purpose &&
      a.beginDate === b.beginDate &&
      a.endDate === b.endDate
    );
  }

  private navigateToDetail(): Promise<boolean> {
    return this.router.navigate(this.detailLink());
  }
}
