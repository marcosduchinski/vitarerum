import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  resource,
  signal,
} from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { MenuItem } from 'primeng/api';
import { firstValueFrom } from 'rxjs';

import { ApiError, toApiError } from '@core/http/api-error.model';
import { EmptyStateComponent } from '@shared/components/empty-state/empty-state.component';
import { ErrorMessageComponent } from '@shared/components/error-message/error-message.component';
import { LoadingStateComponent } from '@shared/components/loading-state/loading-state.component';
import { PageHeaderComponent } from '@shared/components/page-header/page-header.component';
import { RowActionsComponent } from '@shared/components/row-actions/row-actions.component';

import { MuseumQuestion, MuseumQuestionStatus } from '../models/museum-question.model';
import { MUSEUM_QUESTION_MANAGEMENT_SERVICE } from '../services/museum-question-management.service';

const DEFAULT_PAGE_SIZE = 20;
const PAGE_SIZE_OPTIONS = [10, 20, 50, 100] as const;
const STATUS_OPTIONS: readonly { value: MuseumQuestionStatus | ''; label: string }[] = [
  { value: 'SUBMITTED', label: 'Submitted' },
  { value: 'ANSWERED', label: 'Answered' },
  { value: 'OUT_OF_SCOPE', label: 'Out of scope' },
  { value: 'CLOSED', label: 'Closed' },
  { value: '', label: 'All statuses' },
];

const STATUS_LABELS: Record<MuseumQuestionStatus, string> = {
  SUBMITTED: 'Submitted',
  ANSWERED: 'Answered',
  OUT_OF_SCOPE: 'Out of scope',
  CLOSED: 'Closed',
};

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
  ],
  templateUrl: './museum-questions-page.component.html',
  styleUrl: './museum-questions-page.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class MuseumQuestionsPageComponent {
  private readonly service = inject(MUSEUM_QUESTION_MANAGEMENT_SERVICE);
  private readonly router = inject(Router);

  protected readonly statusOptions = STATUS_OPTIONS;
  protected readonly currentPage = signal(0);
  protected readonly pageSize = signal(DEFAULT_PAGE_SIZE);
  protected readonly statusFilter = signal<MuseumQuestionStatus | ''>('SUBMITTED');
  protected readonly pageSizeOptions = PAGE_SIZE_OPTIONS;

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
          status: params.status,
        }),
      ),
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

  protected actionItemsFor(question: MuseumQuestion): MenuItem[] {
    const questionId = question.id;
    return [
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
}
