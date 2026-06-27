import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  input,
  resource,
  signal,
} from '@angular/core';
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
import { CreateInSituVisitReportModalComponent } from '../../../reports/components/create-in-situ-visit-report-modal/create-in-situ-visit-report-modal.component';
import {
  CreateInSituVisitReportRequest,
  InSituVisitReport,
} from '../../../reports/models/report.model';
import { REPORTS_API_SERVICE } from '../../../reports/services/reports-api.service';
import { PROJECT_API_SERVICE } from '../../services/project-api.service';

type StaffProjectPanel = 'overview' | 'tasks' | 'todo';

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

  protected readonly activePanel = signal<StaffProjectPanel>('overview');
  protected readonly acting = signal(false);
  protected readonly actionError = signal<ApiError | null>(null);
  protected readonly cancelConfirmOpen = signal(false);
  protected readonly reportModalOpen = signal(false);
  protected readonly reportCreating = signal(false);
  protected readonly reportError = signal<ApiError | null>(null);
  protected readonly createdReport = signal<InSituVisitReport | null>(null);

  protected readonly formatDate = formatDate;
  protected readonly formatDateTime = formatDateTime;

  protected asWorkflowStatus(value: string): WorkflowStatus {
    return value as WorkflowStatus;
  }

  protected selectPanel(panel: StaffProjectPanel): void {
    this.activePanel.set(panel);
  }

  protected openCancelConfirm(): void {
    if (!this.canCancel()) return;
    this.actionError.set(null);
    this.cancelConfirmOpen.set(true);
  }

  protected closeCancelConfirm(): void {
    this.cancelConfirmOpen.set(false);
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
