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
import { IDENTITY_SERVICE } from '@core/auth/identity.service';
import { firstValueFrom } from 'rxjs';

import { ApiError, toApiError } from '@core/http/api-error.model';
import { ConfirmModalComponent } from '@shared/components/confirm-modal/confirm-modal.component';
import { ErrorMessageComponent } from '@shared/components/error-message/error-message.component';
import { LoadingStateComponent } from '@shared/components/loading-state/loading-state.component';
import {
  StatusChipComponent,
  WorkflowStatus,
} from '@shared/components/status-chip/status-chip.component';
import { TypeChipComponent } from '@shared/components/type-chip/type-chip.component';
import { UseType } from '@shared/models/collection-use-status.model';

import { PROJECT_API_SERVICE } from '../../services/project-api.service';

type ExternalProjectPanel = 'overview' | 'tasks';

const LOG_ROUTE: Record<UseType, string> = {
  IN_SITU_VISIT: 'research',
  EXHIBITION: 'exhibition',
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

const START_NOTE = 'Started from project detail.';
const CANCEL_REASON = 'Cancelled from project detail.';
const COMPLETE_NOTE = 'Completed from project detail.';

@Component({
  selector: 'app-project-detail-page',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    RouterLink,
    LoadingStateComponent,
    ErrorMessageComponent,
    StatusChipComponent,
    TypeChipComponent,
    ConfirmModalComponent,
  ],
  templateUrl: './project-detail-page.component.html',
  styleUrl: './project-detail-page.component.scss',
})
export class ProjectDetailPageComponent {
  private readonly projectService = inject(PROJECT_API_SERVICE);
  private readonly router = inject(Router);
  private readonly identity = inject(IDENTITY_SERVICE);

  readonly id = input.required<string>();
  readonly returnTo = input<string>();
  readonly returnLabel = input<string>();

  protected readonly backLink = computed(() => safeReturnTo(this.returnTo()));
  protected readonly backLabel = computed(() => `Back to ${safeReturnLabel(this.returnLabel())}`);

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

  protected readonly logRoute = computed(() => {
    const type = this.project()?.type;
    return type ? LOG_ROUTE[type] : 'research';
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

  protected readonly canStart = computed(
    () => this.identity.session()?.group === 'EXTERNAL' && this.project()?.status === 'CREATED',
  );
  protected readonly canComplete = computed(() => this.project()?.status === 'IN_PROGRESS');
  protected readonly canCancel = computed(
    () => this.project()?.status === 'CREATED' || this.project()?.status === 'IN_PROGRESS',
  );
  protected readonly canLog = computed(() => this.project()?.status === 'IN_PROGRESS');
  // The publication log stays reachable while in progress (researcher writes) and
  // once completed (researcher reads staff entries).
  protected readonly canOpenPublication = computed(() => {
    const status = this.project()?.status;
    return status === 'IN_PROGRESS' || status === 'COMPLETED';
  });

  protected readonly activePanel = signal<ExternalProjectPanel>('overview');
  protected readonly acting = signal(false);
  protected readonly actionError = signal<ApiError | null>(null);
  protected readonly startConfirmOpen = signal(false);
  protected readonly completeConfirmOpen = signal(false);
  protected readonly cancelConfirmOpen = signal(false);

  protected readonly formatDate = formatDate;
  protected readonly formatDateTime = formatDateTime;

  protected asWorkflowStatus(value: string): WorkflowStatus {
    return value as WorkflowStatus;
  }

  protected selectPanel(panel: ExternalProjectPanel): void {
    this.activePanel.set(panel);
  }

  protected openStartConfirm(): void {
    if (!this.canStart()) return;
    this.startConfirmOpen.set(true);
  }
  protected closeStartConfirm(): void {
    this.startConfirmOpen.set(false);
  }
  protected openCompleteConfirm(): void {
    if (!this.canComplete()) return;
    this.completeConfirmOpen.set(true);
  }
  protected closeCompleteConfirm(): void {
    this.completeConfirmOpen.set(false);
  }
  protected openCancelConfirm(): void {
    if (!this.canCancel()) return;
    this.cancelConfirmOpen.set(true);
  }
  protected closeCancelConfirm(): void {
    this.cancelConfirmOpen.set(false);
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
      await firstValueFrom(this.projectService.cancelProject(this.id(), { reason: CANCEL_REASON }));
      await this.router.navigate(['/p/collections/projects/cancelled']);
    } catch (err) {
      this.actionError.set(toApiError(err));
    } finally {
      this.cancelConfirmOpen.set(false);
      this.acting.set(false);
    }
  }
}
