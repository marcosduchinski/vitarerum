import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  resource,
  signal,
} from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { MenuItem } from 'primeng/api';
import { firstValueFrom } from 'rxjs';

import { ApiError, toApiError } from '@core/http/api-error.model';
import { GroupName } from '@core/auth/models/group-name.enum';
import { groupNameOf } from '@core/auth/models/permission.model';
import { USER_MANAGEMENT_SERVICE } from '@features/admin/services/user-management.service';
import { ConfirmModalComponent } from '@shared/components/confirm-modal/confirm-modal.component';
import { EmptyStateComponent } from '@shared/components/empty-state/empty-state.component';
import { ErrorMessageComponent } from '@shared/components/error-message/error-message.component';
import { LoadingStateComponent } from '@shared/components/loading-state/loading-state.component';
import { PageHeaderComponent } from '@shared/components/page-header/page-header.component';
import { RowActionsComponent } from '@shared/components/row-actions/row-actions.component';

import { MuseumQuestionListItem, MuseumQuestionStatus } from '../models/museum-question.model';
import { MUSEUM_QUESTION_MANAGEMENT_SERVICE } from '../services/museum-question-management.service';

const DEFAULT_PAGE_SIZE = 20;
const PAGE_SIZE_OPTIONS = [10, 20, 50, 100] as const;
const STATUS_OPTIONS: readonly { value: MuseumQuestionStatus | ''; label: string }[] = [
  { value: 'SUBMITTED', label: 'Submitted' },
  { value: 'IN_PROGRESS', label: 'In progress' },
  { value: 'ANSWERED', label: 'Answered' },
  { value: 'OUT_OF_SCOPE', label: 'Out of scope' },
  { value: 'CLOSED', label: 'Closed' },
  { value: '', label: 'All statuses' },
];
const STATUS_LABELS: Record<MuseumQuestionStatus, string> = {
  SUBMITTED: 'Submitted',
  IN_PROGRESS: 'In progress',
  ANSWERED: 'Answered',
  OUT_OF_SCOPE: 'Out of scope',
  CLOSED: 'Closed',
};

const GROUP_LABELS: Partial<Record<GroupName, string>> = {
  CURATORIAL: 'Curatorial',
  COLLECTIONS_MANAGEMENT: 'Collections management',
};

interface ForwardStaffOption {
  readonly label: string;
  readonly permissionId: string;
}

type MuseumQuestionListMode = 'all' | 'new';

@Component({
  selector: 'app-museum-questions-page',
  standalone: true,
  imports: [
    RouterLink,
    PageHeaderComponent,
    LoadingStateComponent,
    ErrorMessageComponent,
    EmptyStateComponent,
    RowActionsComponent,
    ConfirmModalComponent,
  ],
  templateUrl: './museum-questions-page.component.html',
  styleUrl: './museum-questions-page.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class MuseumQuestionsPageComponent {
  private readonly service = inject(MUSEUM_QUESTION_MANAGEMENT_SERVICE);
  private readonly userService = inject(USER_MANAGEMENT_SERVICE);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);
  private readonly mode = (this.route.snapshot.data['museumQuestionListMode'] ??
    'all') as MuseumQuestionListMode;

  protected readonly statusOptions = STATUS_OPTIONS;
  protected readonly currentPage = signal(0);
  protected readonly pageSize = signal(DEFAULT_PAGE_SIZE);
  protected readonly statusFilter = signal<MuseumQuestionStatus | ''>('SUBMITTED');
  protected readonly pageSizeOptions = PAGE_SIZE_OPTIONS;
  protected readonly isNewInquiriesMode = this.mode === 'new';
  protected readonly headerTitle = this.isNewInquiriesMode ? 'New inquiries' : 'All enquiries';
  protected readonly headerDescription = this.isNewInquiriesMode
    ? 'Submitted public enquiries waiting to be forwarded.'
    : 'Review public messages submitted through Ask the Museum.';
  protected readonly emptyTitle = this.isNewInquiriesMode
    ? 'No new inquiries'
    : 'No questions found';
  protected readonly emptyMessage = this.isNewInquiriesMode
    ? 'There are no submitted enquiries waiting to be forwarded.'
    : 'There are no messages for the selected status.';

  protected readonly questionsResource = resource({
    params: () => ({
      page: this.currentPage(),
      size: this.pageSize(),
      status: this.statusFilter(),
    }),
    loader: ({ params }) =>
      firstValueFrom(
        this.service.list({
          page: params.page,
          size: params.size,
          status: this.isNewInquiriesMode ? 'SUBMITTED' : params.status,
          unassignedOnly: this.isNewInquiriesMode,
        }),
      ),
  });

  protected readonly usersResource = resource({
    loader: () => firstValueFrom(this.userService.listUsers({ size: 100 })),
  });

  protected readonly questions = computed(() => this.questionsResource.value()?.content ?? []);
  protected readonly totalQuestions = computed(
    () => this.questionsResource.value()?.totalElements ?? 0,
  );
  protected readonly totalPages = computed(() => this.questionsResource.value()?.totalPages ?? 0);
  protected readonly rangeStart = computed(() =>
    this.totalQuestions() === 0 ? 0 : this.currentPage() * this.pageSize() + 1,
  );
  protected readonly rangeEnd = computed(() =>
    Math.min((this.currentPage() + 1) * this.pageSize(), this.totalQuestions()),
  );
  protected readonly listError = computed<ApiError | null>(() => {
    const err = this.questionsResource.error();
    return err ? toApiError(err) : null;
  });
  protected readonly staffOptions = computed<ForwardStaffOption[]>(() =>
    (this.usersResource.value()?.content ?? []).flatMap((user) =>
      user.permissions.flatMap((permission) => {
        const groupName = groupNameOf(permission.group);
        if (groupName !== 'CURATORIAL' && groupName !== 'COLLECTIONS_MANAGEMENT') return [];
        return [
          {
            label: `${user.name} — ${GROUP_LABELS[groupName]}`,
            permissionId: permission.permissionId,
          },
        ];
      }),
    ),
  );

  protected actionItemsFor(question: MuseumQuestionListItem): MenuItem[] {
    const questionId = question.id;
    return [
      ...(question.status === 'SUBMITTED' && question.assignedTo === null
        ? [
            {
              label: 'Forward',
              icon: 'pi pi-send',
              command: () => this.openForwardModal(questionId),
            },
          ]
        : []),
      {
        label: 'Details',
        icon: 'pi pi-eye',
        command: () => {
          void this.router.navigate(['/p/museum-questions', questionId]);
        },
      },
    ];
  }

  protected onStatusFilterChange(event: Event): void {
    this.statusFilter.set((event.target as HTMLSelectElement).value as MuseumQuestionStatus | '');
    this.currentPage.set(0);
  }

  protected readonly forwardModalQuestionId = signal<string | null>(null);
  protected readonly forwardModalQuestion = computed(() => {
    const questionId = this.forwardModalQuestionId();
    return this.questions().find((question) => question.id === questionId) ?? null;
  });
  protected readonly forwardTargetPermissionId = signal('');
  protected readonly forwardTargetLabel = computed(
    () =>
      this.staffOptions().find((option) => option.permissionId === this.forwardTargetPermissionId())
        ?.label ?? 'the selected staff member',
  );
  protected readonly forwardPending = signal(false);
  protected readonly forwardError = signal<ApiError | null>(null);
  protected readonly forwardSuccessMessage = signal<string | null>(null);

  protected openForwardModal(questionId: string): void {
    this.forwardModalQuestionId.set(questionId);
    this.forwardTargetPermissionId.set('');
    this.forwardError.set(null);
  }

  protected closeForwardModal(): void {
    if (this.forwardPending()) return;
    this.forwardModalQuestionId.set(null);
  }

  protected onForwardTargetChange(event: Event): void {
    this.forwardTargetPermissionId.set((event.target as HTMLSelectElement).value);
  }

  protected dismissForwardSuccess(): void {
    this.forwardSuccessMessage.set(null);
  }

  protected async forward(questionId: string): Promise<void> {
    const targetPermissionId = this.forwardTargetPermissionId();
    if (!targetPermissionId || this.forwardPending()) return;
    const subject = this.forwardModalQuestion()?.subject ?? 'The enquiry';
    this.forwardPending.set(true);
    this.forwardError.set(null);
    try {
      await firstValueFrom(this.service.forward(questionId, { targetPermissionId }));
      this.forwardModalQuestionId.set(null);
      this.forwardSuccessMessage.set(`${subject} was forwarded to ${this.forwardTargetLabel()}.`);
      this.questionsResource.reload();
    } catch (err) {
      this.forwardError.set(toApiError(err));
    } finally {
      this.forwardPending.set(false);
    }
  }

  protected onPageSizeChange(event: Event): void {
    this.pageSize.set(Number((event.target as HTMLSelectElement).value));
    this.currentPage.set(0);
  }

  protected firstPage(): void {
    this.currentPage.set(0);
  }

  protected previousPage(): void {
    this.currentPage.update((page) => Math.max(0, page - 1));
  }

  protected nextPage(): void {
    this.currentPage.update((page) => Math.min(Math.max(0, this.totalPages() - 1), page + 1));
  }

  protected lastPage(): void {
    this.currentPage.set(Math.max(0, this.totalPages() - 1));
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
