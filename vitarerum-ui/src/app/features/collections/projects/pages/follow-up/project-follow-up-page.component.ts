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

import {
  CollectionUseProjectObject,
  CreateFollowUpProjectRequest,
} from '../../models/project.model';
import { PROJECT_API_SERVICE } from '../../services/project-api.service';

interface FollowUpFormModel {
  readonly title: string;
  readonly purpose: string;
  readonly beginDate: string;
  readonly endDate: string;
  readonly note: string;
}

const EMPTY_FORM: FollowUpFormModel = {
  title: '',
  purpose: '',
  beginDate: '',
  endDate: '',
  note: '',
};

const STAFF_DETAIL_SECTIONS = ['collections', 'curatorial', 'direction'] as const;
type StaffDetailSection = (typeof STAFF_DETAIL_SECTIONS)[number];

function safeSection(value: string | null): StaffDetailSection {
  return (STAFF_DETAIL_SECTIONS as readonly string[]).includes(value ?? '')
    ? (value as StaffDetailSection)
    : 'collections';
}

@Component({
  selector: 'app-project-follow-up-page',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    RouterLink,
    FormField,
    LoadingStateComponent,
    ErrorMessageComponent,
    StatusChipComponent,
  ],
  templateUrl: './project-follow-up-page.component.html',
  styleUrl: './project-follow-up-page.component.scss',
})
export class ProjectFollowUpPageComponent {
  private readonly projectService = inject(PROJECT_API_SERVICE);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);
  private loadedProjectId: string | null = null;

  readonly id = input.required<string>();

  // Which staff section (collections/curatorial/direction) the "Create
  // follow-up project" action was triggered from — carried via `?section=`
  // since this route isn't itself section-prefixed (unlike the edit routes).
  // Falls back to 'collections' when absent or unrecognised.
  protected readonly section = computed(() =>
    safeSection(this.route.snapshot.queryParamMap.get('section')),
  );

  protected readonly projectResource = resource({
    params: () => this.id(),
    loader: ({ params }) => firstValueFrom(this.projectService.getProject(params)),
  });
  protected readonly project = computed(() => this.projectResource.value() ?? null);
  protected readonly loadError = computed<ApiError | null>(() => {
    const error = this.projectResource.error();
    return error ? toApiError(error) : null;
  });
  protected readonly objects = computed(() => this.project()?.objects ?? []);
  protected readonly selectedObjectIds = signal<ReadonlySet<string>>(new Set<string>());
  protected readonly pending = signal(false);
  protected readonly createError = signal<ApiError | null>(null);
  protected readonly submitted = signal(false);
  protected readonly formModel = signal<FollowUpFormModel>({ ...EMPTY_FORM });
  protected readonly detailLink = computed(() => [
    '/p/collections/projects',
    this.section(),
    this.id(),
  ]);

  protected readonly followUpForm = form(this.formModel, (path) => {
    validate(path.title, ({ value }) =>
      value().trim() ? undefined : { kind: 'required', message: 'Title is required.' },
    );
    validate(path.purpose, ({ value }) =>
      value().trim() ? undefined : { kind: 'required', message: 'Purpose is required.' },
    );
    validate(path.beginDate, ({ value }) =>
      value() ? undefined : { kind: 'required', message: 'Begin date is required.' },
    );
    validate(path.endDate, ({ value, valueOf }) => {
      const beginDate = valueOf(path.beginDate);
      const endDate = value();
      if (!endDate) return { kind: 'required', message: 'End date is required.' };
      return beginDate && endDate < beginDate
        ? { kind: 'date-range', message: 'End date cannot precede begin date.' }
        : undefined;
    });
  });

  protected readonly canCreate = computed(() => this.project()?.status === 'COMPLETED');
  protected readonly allSelected = computed(() => {
    const objects = this.objects();
    return objects.length > 0 && objects.every((object) => this.isSelected(object.id));
  });
  protected readonly objectSelectionInvalid = computed(
    () => this.submitted() && this.selectedObjectIds().size === 0,
  );
  protected readonly createDisabled = computed(
    () =>
      this.pending() ||
      !this.project() ||
      !this.canCreate() ||
      this.followUpForm().invalid() ||
      this.selectedObjectIds().size === 0,
  );

  private readonly syncForm = effect(() => {
    const project = this.project();
    if (!project || this.loadedProjectId === project.id) return;

    this.loadedProjectId = project.id;
    this.formModel.set({
      title: project.title.trim(),
      purpose: project.purpose.trim(),
      beginDate: '',
      endDate: '',
      note: '',
    });
    this.selectedObjectIds.set(new Set((project.objects ?? []).map((object) => object.id)));
    this.createError.set(null);
    this.submitted.set(false);
  });

  protected asWorkflowStatus(value: string): WorkflowStatus {
    return value as WorkflowStatus;
  }

  protected isSelected(objectId: string): boolean {
    return this.selectedObjectIds().has(objectId);
  }

  protected toggleObject(objectId: string, checked: boolean): void {
    const next = new Set(this.selectedObjectIds());
    if (checked) next.add(objectId);
    else next.delete(objectId);
    this.selectedObjectIds.set(next);
  }

  protected toggleAll(checked: boolean): void {
    this.selectedObjectIds.set(
      checked ? new Set(this.objects().map((object) => object.id)) : new Set<string>(),
    );
  }

  protected async create(event: Event): Promise<void> {
    event.preventDefault();
    this.submitted.set(true);
    this.followUpForm().markAsTouched();
    if (this.createDisabled()) return;

    this.pending.set(true);
    this.createError.set(null);
    try {
      const created = await firstValueFrom(
        this.projectService.createFollowUpProject(this.id(), this.buildRequest()),
      );
      await this.router.navigate(['/p/collections/projects', this.section(), created.id]);
    } catch (error) {
      this.createError.set(toApiError(error));
    } finally {
      this.pending.set(false);
    }
  }

  protected cancel(): void {
    if (this.pending()) return;
    void this.router.navigate(this.detailLink());
  }

  protected objectLabel(object: CollectionUseProjectObject): string {
    return object.displayTitle?.trim() || object.objectName?.trim() || object.inventoryNumber;
  }

  private buildRequest(): CreateFollowUpProjectRequest {
    const value = this.formModel();
    return {
      title: value.title.trim(),
      purpose: value.purpose.trim(),
      beginDate: value.beginDate,
      endDate: value.endDate,
      note: value.note.trim() || null,
      objectIds: [...this.selectedObjectIds()],
    };
  }
}
