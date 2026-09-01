import { ChangeDetectionStrategy, Component, computed, inject, resource } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { MenuItem } from 'primeng/api';
import { firstValueFrom } from 'rxjs';

import { IDENTITY_SERVICE } from '@core/auth/identity.service';
import { ApiError, toApiError } from '@core/http/api-error.model';
import { EmptyStateComponent } from '@shared/components/empty-state/empty-state.component';
import { ErrorMessageComponent } from '@shared/components/error-message/error-message.component';
import { LoadingStateComponent } from '@shared/components/loading-state/loading-state.component';
import { PageHeaderComponent } from '@shared/components/page-header/page-header.component';
import { RowActionsComponent } from '@shared/components/row-actions/row-actions.component';

import { MuseumQuestionListItem, MuseumQuestionStatus } from '../../models/museum-question.model';
import { MUSEUM_QUESTION_MANAGEMENT_SERVICE } from '../../services/museum-question-management.service';

const STATUS_LABELS: Record<MuseumQuestionStatus, string> = {
  SUBMITTED: 'Submitted',
  IN_PROGRESS: 'In progress',
  ANSWERED: 'Answered',
  OUT_OF_SCOPE: 'Out of scope',
  CLOSED: 'Closed',
};

@Component({
  selector: 'app-my-inquiries-page',
  standalone: true,
  imports: [
    RouterLink,
    PageHeaderComponent,
    LoadingStateComponent,
    ErrorMessageComponent,
    EmptyStateComponent,
    RowActionsComponent,
  ],
  templateUrl: './my-inquiries-page.component.html',
  styleUrl: './my-inquiries-page.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class MyInquiriesPageComponent {
  private readonly service = inject(MUSEUM_QUESTION_MANAGEMENT_SERVICE);
  private readonly identity = inject(IDENTITY_SERVICE);
  private readonly router = inject(Router);

  protected readonly permissionId = computed(() => this.identity.getPermissionId());

  protected readonly questionsResource = resource({
    params: () => ({ assignedTo: this.permissionId() }),
    loader: ({ params }) => {
      if (!params.assignedTo) {
        return Promise.resolve({ content: [], page: 0, size: 20, totalElements: 0, totalPages: 0 });
      }
      return firstValueFrom(
        this.service.list({
          assignedTo: params.assignedTo,
          status: 'IN_PROGRESS',
          page: 0,
          size: 100,
        }),
      );
    },
  });

  protected readonly questions = computed(() => this.questionsResource.value()?.content ?? []);
  protected readonly totalQuestions = computed(
    () => this.questionsResource.value()?.totalElements ?? 0,
  );
  protected readonly listError = computed<ApiError | null>(() => {
    const err = this.questionsResource.error();
    return err ? toApiError(err) : null;
  });

  protected actionItemsFor(question: MuseumQuestionListItem): MenuItem[] {
    return [
      {
        label: 'Details',
        icon: 'pi pi-eye',
        command: () => {
          void this.router.navigate(['/p/museum-questions', question.id]);
        },
      },
    ];
  }

  protected statusLabel(status: MuseumQuestionStatus): string {
    return STATUS_LABELS[status];
  }

  protected formatDate(value: string | null): string {
    if (!value) return '-';
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: 'medium',
      timeStyle: 'short',
    }).format(new Date(value));
  }

  protected dueLabel(question: MuseumQuestionListItem): string {
    const due = this.formatDate(question.responseDueAt);
    return question.responseOverdue ? `Overdue · ${due}` : due;
  }
}
