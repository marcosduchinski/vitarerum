import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  input,
  resource,
  signal,
} from '@angular/core';
import { HttpErrorResponse } from '@angular/common/http';
import { Router, RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { IDENTITY_SERVICE } from '@core/auth/identity.service';
import { ApiError, toApiError } from '@core/http/api-error.model';
import { ConfirmModalComponent } from '@shared/components/confirm-modal/confirm-modal.component';
import { ErrorMessageComponent } from '@shared/components/error-message/error-message.component';
import { FeedbackMessageComponent } from '@shared/components/feedback-message/feedback-message.component';
import { LoadingStateComponent } from '@shared/components/loading-state/loading-state.component';
import {
  StatusChipComponent,
  WorkflowStatus,
} from '@shared/components/status-chip/status-chip.component';
import { TypeChipComponent } from '@shared/components/type-chip/type-chip.component';
import { UseType } from '@shared/models/collection-use-status.model';

import { ProjectTodoListComponent } from '../../components/project-todo-list/project-todo-list.component';
import { ProjectObjectsSectionComponent } from '../../components/project-objects-section/project-objects-section.component';
import { CreateInSituVisitReportModalComponent } from '../../../reports/components/create-in-situ-visit-report-modal/create-in-situ-visit-report-modal.component';
import {
  CreateInSituVisitReportRequest,
  InSituVisitReport,
} from '../../../reports/models/report.model';
import {
  AddProjectObjectsRequest,
  ProjectObjectDependencySummary,
} from '../../models/project.model';
import { REPORTS_API_SERVICE } from '../../../reports/services/reports-api.service';
import { PROJECT_API_SERVICE } from '../../services/project-api.service';

const LOG_ROUTE_SEGMENTS: Record<UseType, string> = {
  EXHIBITION: 'exhibition',
  IN_SITU_VISIT: 'research',
  OTHER: 'other',
};

function safeReturnTo(value: string | undefined): string {
  return value?.startsWith('/p/collections') ? value : '/p/collections/projects/my';
}

function safeReturnLabel(value: string | undefined): string {
  const trimmed = value?.trim();
  return trimmed ? trimmed : 'my projects';
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString('en-GB', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
    });
  } catch {
    return iso;
  }
}

function formatDateTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString('en-GB', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

const START_NOTE = 'Started from staff project detail.';
const COMPLETE_NOTE = 'Completed from staff project detail.';
type ProjectDetailTab = 'actions' | 'objects' | 'todo';
const PROJECT_DETAIL_TABS: readonly ProjectDetailTab[] = ['actions', 'objects', 'todo'];
const EMPTY_PROJECT_OBJECT_DEPENDENCIES: ProjectObjectDependencySummary = {
  accessLogEntries: 0,
  occurrenceEntries: 0,
  publicationEntries: 0,
  attachments: 0,
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function numericValue(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : 0;
}

function extractProjectObjectDependencySummary(
  error: unknown,
): ProjectObjectDependencySummary | null {
  const body = error instanceof HttpErrorResponse ? error.error : error;
  if (!isRecord(body)) return null;

  const errorCode = typeof body['error'] === 'string' ? body['error'] : null;
  if (errorCode !== 'PROJECT_OBJECT_HAS_DEPENDENCIES') return null;

  const dependencies = body['dependencies'];
  if (!isRecord(dependencies)) return EMPTY_PROJECT_OBJECT_DEPENDENCIES;

  return {
    accessLogEntries: numericValue(dependencies['accessLogEntries']),
    occurrenceEntries: numericValue(dependencies['occurrenceEntries']),
    publicationEntries: numericValue(dependencies['publicationEntries']),
    attachments: numericValue(dependencies['attachments']),
  };
}

@Component({
  selector: 'app-project-staff-detail-page',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    RouterLink,
    LoadingStateComponent,
    ErrorMessageComponent,
    FeedbackMessageComponent,
    StatusChipComponent,
    TypeChipComponent,
    ConfirmModalComponent,
    CreateInSituVisitReportModalComponent,
    ProjectObjectsSectionComponent,
    ProjectTodoListComponent,
  ],
  templateUrl: './project-staff-detail-page.component.html',
  styleUrl: './project-staff-detail-page.component.scss',
})
export class ProjectStaffDetailPageComponent {
  private readonly projectService = inject(PROJECT_API_SERVICE);
  private readonly reportsService = inject(REPORTS_API_SERVICE);
  private readonly identity = inject(IDENTITY_SERVICE);
  private readonly router = inject(Router);

  readonly id = input.required<string>();
  readonly returnTo = input<string>();
  readonly returnLabel = input<string>();
  readonly sectionLabel = input('Staff');

  protected readonly backLink = computed(() => safeReturnTo(this.returnTo()));
  protected readonly backLabel = computed(() => `Back to ${safeReturnLabel(this.returnLabel())}`);
  protected readonly cancelReason = computed(
    () => `Cancelled from ${this.sectionLabel().toLowerCase()} project detail.`,
  );

  protected readonly projectResource = resource({
    params: () => this.id(),
    loader: ({ params }) => firstValueFrom(this.projectService.getProject(params)),
  });

  protected readonly eventsResource = resource({
    params: () => this.id(),
    loader: ({ params }) => firstValueFrom(this.projectService.listEvents(params)),
  });

  protected readonly project = computed(() => this.projectResource.value() ?? null);
  protected readonly events = computed(() => this.eventsResource.value()?.content ?? []);
  protected readonly projectError = computed<ApiError | null>(() => {
    const err = this.projectResource.error();
    return err ? toApiError(err) : null;
  });
  protected readonly canCancel = computed(() => {
    const project = this.project();
    if (!project) return false;

    return (
      project.actions?.canCancel ??
      (project.status === 'CREATED' || project.status === 'IN_PROGRESS')
    );
  });
  protected readonly canStart = computed(() => {
    const project = this.project();
    if (!project) return false;

    return project.actions?.canStart ?? project.status === 'CREATED';
  });
  protected readonly canComplete = computed(() => {
    const project = this.project();
    if (!project) return false;

    return project.actions?.canComplete ?? project.status === 'IN_PROGRESS';
  });
  protected readonly canEditProject = computed(() => {
    const status = this.project()?.status;
    return status === 'CREATED' || status === 'IN_PROGRESS';
  });
  protected readonly editLink = computed(() => {
    const label = this.sectionLabel().toLowerCase();
    const section = label.includes('curatorial')
      ? 'curatorial'
      : label.includes('direction')
        ? 'direction'
        : 'collections';
    return ['/p/collections/projects', section, this.id(), 'edit'];
  });
  protected readonly canCreateFollowUp = computed(() => this.project()?.status === 'COMPLETED');
  protected readonly canOpenLogTasks = computed(() => this.project()?.status === 'IN_PROGRESS');
  // Staff write publication entries once COMPLETED; the log stays readable in
  // both phases, so surface the task for IN_PROGRESS and COMPLETED projects.
  protected readonly canOpenPublication = computed(() => {
    const status = this.project()?.status;
    return status === 'IN_PROGRESS' || status === 'COMPLETED';
  });
  protected readonly canCreateInSituVisitReport = computed(() => {
    const project = this.project();
    const group = this.identity.session()?.group;
    return (
      project?.type === 'IN_SITU_VISIT' &&
      project.status === 'COMPLETED' &&
      (group === 'CURATORIAL' || group === 'COLLECTIONS_MANAGEMENT')
    );
  });
  protected readonly logRouteSegment = computed(() => {
    const type = this.project()?.type;
    return type ? LOG_ROUTE_SEGMENTS[type] : 'research';
  });

  protected readonly isCancelled = computed(() => this.project()?.status === 'CANCELLED');

  // Drives the lifecycle rail at the top of the Actions panel. Cancelled is a
  // terminal off-shoot, so it leaves every forward step un-reached.
  protected readonly lifecycle = computed(() => {
    const status = this.project()?.status ?? 'CREATED';
    const steps = [
      { key: 'CREATED', label: 'Created' },
      { key: 'IN_PROGRESS', label: 'In progress' },
      { key: 'COMPLETED', label: 'Completed' },
    ] as const;
    const currentIndex = this.isCancelled() ? -1 : steps.findIndex((s) => s.key === status);
    return steps.map((step, index) => ({
      label: step.label,
      done: currentIndex > index,
      current: currentIndex === index,
    }));
  });

  protected readonly acting = signal(false);
  protected readonly actionError = signal<ApiError | null>(null);
  protected readonly startConfirmOpen = signal(false);
  protected readonly completeConfirmOpen = signal(false);
  protected readonly cancelConfirmOpen = signal(false);
  protected readonly reportModalOpen = signal(false);
  protected readonly reportCreating = signal(false);
  protected readonly reportError = signal<ApiError | null>(null);
  protected readonly createdReport = signal<InSituVisitReport | null>(null);
  protected readonly addingObjects = signal(false);
  protected readonly removingObjectId = signal<string | null>(null);
  protected readonly addObjectsError = signal<ApiError | null>(null);
  protected readonly removeObjectError = signal<ApiError | null>(null);
  protected readonly cascadeRemoveObjectId = signal<string | null>(null);
  protected readonly cascadeRemoveDependencies = signal<ProjectObjectDependencySummary | null>(
    null,
  );
  protected readonly cascadeRemoveReason = signal('');
  protected readonly cascadeRemoveError = signal<ApiError | null>(null);
  protected readonly activeTab = signal<ProjectDetailTab>('actions');
  protected readonly cascadeRemoveObjectName = computed(() => {
    const objectId = this.cascadeRemoveObjectId();
    const object = this.project()?.objects?.find((item) => item.id === objectId);
    return object?.displayTitle ?? object?.objectName ?? object?.inventoryNumber ?? 'this object';
  });
  protected readonly cascadeRemoveReasonInvalid = computed(
    () => this.cascadeRemoveReason().trim().length === 0,
  );
  protected readonly cascadeRemoveSummary = computed(() => {
    const dependencies = this.cascadeRemoveDependencies() ?? EMPTY_PROJECT_OBJECT_DEPENDENCIES;
    return [
      `Access log entries: ${dependencies.accessLogEntries}`,
      `Occurrence entries: ${dependencies.occurrenceEntries}`,
      `Publication entries: ${dependencies.publicationEntries}`,
      `Attachments: ${dependencies.attachments}`,
    ].join(' · ');
  });

  protected readonly formatDate = formatDate;
  protected readonly formatDateTime = formatDateTime;

  protected asWorkflowStatus(value: string): WorkflowStatus {
    return value as WorkflowStatus;
  }

  protected selectTab(tab: ProjectDetailTab): void {
    this.activeTab.set(tab);
  }

  protected onTabKeydown(event: KeyboardEvent, index: number): void {
    const lastIndex = PROJECT_DETAIL_TABS.length - 1;
    let nextIndex: number | null = null;

    if (event.key === 'ArrowRight') {
      nextIndex = index === lastIndex ? 0 : index + 1;
    } else if (event.key === 'ArrowLeft') {
      nextIndex = index === 0 ? lastIndex : index - 1;
    } else if (event.key === 'Home') {
      nextIndex = 0;
    } else if (event.key === 'End') {
      nextIndex = lastIndex;
    }

    if (nextIndex === null) return;
    event.preventDefault();
    this.activeTab.set(PROJECT_DETAIL_TABS[nextIndex]);
  }

  protected openCancelConfirm(): void {
    if (!this.canCancel()) return;
    this.actionError.set(null);
    this.cancelConfirmOpen.set(true);
  }

  protected closeCancelConfirm(): void {
    this.cancelConfirmOpen.set(false);
  }

  protected openStartConfirm(): void {
    if (!this.canStart()) return;
    this.actionError.set(null);
    this.startConfirmOpen.set(true);
  }

  protected closeStartConfirm(): void {
    this.startConfirmOpen.set(false);
  }

  protected openCompleteConfirm(): void {
    if (!this.canComplete()) return;
    this.actionError.set(null);
    this.completeConfirmOpen.set(true);
  }

  protected closeCompleteConfirm(): void {
    this.completeConfirmOpen.set(false);
  }

  protected createFollowUpProject(): void {
    if (!this.canCreateFollowUp()) return;
    void this.router.navigate(['/p/collections/projects', this.id(), 'follow-up', 'new']);
  }

  protected openReportModal(): void {
    if (!this.canCreateInSituVisitReport()) return;
    this.reportError.set(null);
    this.createdReport.set(null);
    this.reportModalOpen.set(true);
  }

  protected closeReportModal(): void {
    if (this.reportCreating()) return;
    this.reportError.set(null);
    this.reportModalOpen.set(false);
  }

  protected dismissCreatedReport(): void {
    this.createdReport.set(null);
  }

  protected async createInSituVisitReport(request: CreateInSituVisitReportRequest): Promise<void> {
    if (this.reportCreating() || !this.canCreateInSituVisitReport()) return;

    this.reportCreating.set(true);
    this.reportError.set(null);

    try {
      const report = await firstValueFrom(
        this.reportsService.createInSituVisitReport(this.id(), request),
      );
      this.createdReport.set(report);
      this.reportModalOpen.set(false);
    } catch (err) {
      this.reportError.set(toApiError(err));
    } finally {
      this.reportCreating.set(false);
    }
  }

  protected async addProjectObjects(request: AddProjectObjectsRequest): Promise<void> {
    if (this.addingObjects() || !this.canEditProject()) return;
    this.addingObjects.set(true);
    this.addObjectsError.set(null);
    this.removeObjectError.set(null);
    try {
      await firstValueFrom(this.projectService.addProjectObjects(this.id(), request));
      this.projectResource.reload();
    } catch (err) {
      this.addObjectsError.set(toApiError(err));
    } finally {
      this.addingObjects.set(false);
    }
  }

  protected async removeProjectObject(objectId: string): Promise<void> {
    if (this.removingObjectId() || !this.canEditProject()) return;
    this.removingObjectId.set(objectId);
    this.addObjectsError.set(null);
    this.removeObjectError.set(null);
    this.clearCascadeRemoveState();
    try {
      await firstValueFrom(this.projectService.removeProjectObject(this.id(), objectId));
      this.projectResource.reload();
    } catch (err) {
      const dependencies = extractProjectObjectDependencySummary(err);
      if (dependencies) {
        this.cascadeRemoveObjectId.set(objectId);
        this.cascadeRemoveDependencies.set(dependencies);
        this.cascadeRemoveReason.set('');
        this.cascadeRemoveError.set(null);
      } else {
        this.removeObjectError.set(toApiError(err));
      }
    } finally {
      this.removingObjectId.set(null);
    }
  }

  protected onCascadeRemoveReasonInput(event: Event): void {
    this.cascadeRemoveReason.set((event.target as HTMLTextAreaElement).value);
  }

  protected closeCascadeRemoveConfirm(): void {
    if (this.removingObjectId()) return;
    this.clearCascadeRemoveState();
  }

  protected async confirmCascadeRemove(): Promise<void> {
    const objectId = this.cascadeRemoveObjectId();
    const reason = this.cascadeRemoveReason().trim();
    if (!objectId || !reason || this.removingObjectId() || !this.canEditProject()) return;

    this.removingObjectId.set(objectId);
    this.cascadeRemoveError.set(null);
    this.removeObjectError.set(null);

    try {
      await firstValueFrom(
        this.projectService.removeProjectObjectCascade(this.id(), objectId, {
          confirmCascade: true,
          reason,
        }),
      );
      this.clearCascadeRemoveState();
      this.projectResource.reload();
    } catch (err) {
      this.cascadeRemoveError.set(toApiError(err));
    } finally {
      this.removingObjectId.set(null);
    }
  }

  private clearCascadeRemoveState(): void {
    this.cascadeRemoveObjectId.set(null);
    this.cascadeRemoveDependencies.set(null);
    this.cascadeRemoveReason.set('');
    this.cascadeRemoveError.set(null);
  }

  protected async start(): Promise<void> {
    if (this.acting() || !this.canStart()) return;

    this.acting.set(true);
    this.actionError.set(null);

    try {
      await firstValueFrom(this.projectService.startProject(this.id(), { note: START_NOTE }));
      this.startConfirmOpen.set(false);
      this.projectResource.reload();
      this.eventsResource.reload();
    } catch (err) {
      this.actionError.set(toApiError(err));
      this.startConfirmOpen.set(false);
    } finally {
      this.acting.set(false);
    }
  }

  protected async complete(): Promise<void> {
    if (this.acting() || !this.canComplete()) return;

    this.acting.set(true);
    this.actionError.set(null);

    try {
      await firstValueFrom(this.projectService.completeProject(this.id(), { note: COMPLETE_NOTE }));
      this.completeConfirmOpen.set(false);
      this.projectResource.reload();
      this.eventsResource.reload();
    } catch (err) {
      this.actionError.set(toApiError(err));
      this.completeConfirmOpen.set(false);
    } finally {
      this.acting.set(false);
    }
  }

  protected async cancel(): Promise<void> {
    if (this.acting() || !this.canCancel()) return;

    this.acting.set(true);
    this.actionError.set(null);

    try {
      await firstValueFrom(
        this.projectService.cancelProject(this.id(), { reason: this.cancelReason() }),
      );
      await this.router.navigate(['/p/collections/projects/cancelled']);
    } catch (err) {
      this.actionError.set(toApiError(err));
    } finally {
      this.cancelConfirmOpen.set(false);
      this.acting.set(false);
    }
  }
}
