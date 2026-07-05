import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  resource,
  signal,
} from '@angular/core';
import { firstValueFrom, Observable } from 'rxjs';

import { ApiError, toApiError } from '@core/http/api-error.model';
import { EmptyStateComponent } from '@shared/components/empty-state/empty-state.component';
import { ErrorMessageComponent } from '@shared/components/error-message/error-message.component';
import { LoadingStateComponent } from '@shared/components/loading-state/loading-state.component';
import { PageHeaderComponent } from '@shared/components/page-header/page-header.component';
import { PaginationComponent } from '@shared/components/pagination/pagination.component';

import { MuseumQuestion, MuseumQuestionStatus } from '../models/museum-question.model';
import { MUSEUM_QUESTION_MANAGEMENT_SERVICE } from '../services/museum-question-management.service';

const PAGE_SIZE = 20;
const STATUS_OPTIONS: readonly { value: MuseumQuestionStatus | ''; label: string }[] = [
  { value: '', label: 'All statuses' },
  { value: 'SUBMITTED', label: 'Submitted' },
  { value: 'ANSWERED', label: 'Answered' },
  { value: 'OUT_OF_SCOPE', label: 'Out of scope' },
  { value: 'CLOSED', label: 'Closed' },
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
    PageHeaderComponent,
    LoadingStateComponent,
    ErrorMessageComponent,
    EmptyStateComponent,
    PaginationComponent,
  ],
  templateUrl: './museum-questions-page.component.html',
  styleUrl: './museum-questions-page.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class MuseumQuestionsPageComponent {
  private readonly service = inject(MUSEUM_QUESTION_MANAGEMENT_SERVICE);

  protected readonly statusOptions = STATUS_OPTIONS;
  protected readonly currentPage = signal(0);
  protected readonly statusFilter = signal<MuseumQuestionStatus | ''>('SUBMITTED');
  protected readonly refreshToken = signal(0);
  protected readonly selectedId = signal<string | null>(null);

  protected readonly questionsResource = resource({
    params: () => ({
      page: this.currentPage(),
      size: PAGE_SIZE,
      status: this.statusFilter(),
      refresh: this.refreshToken(),
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

  protected readonly detailResource = resource({
    params: () => ({ id: this.selectedId(), refresh: this.refreshToken() }),
    loader: ({ params }) =>
      params.id ? firstValueFrom(this.service.get(params.id)) : Promise.resolve(null),
  });

  protected readonly questions = computed(() => this.questionsResource.value()?.content ?? []);
  protected readonly totalQuestions = computed(
    () => this.questionsResource.value()?.totalElements ?? 0,
  );
  protected readonly totalPages = computed(() => this.questionsResource.value()?.totalPages ?? 0);
  protected readonly selectedQuestion = computed(() => this.detailResource.value());
  protected readonly listError = computed<ApiError | null>(() => {
    const err = this.questionsResource.error();
    return err ? toApiError(err) : null;
  });
  protected readonly detailError = computed<ApiError | null>(() => {
    const err = this.detailResource.error();
    return err ? toApiError(err) : null;
  });

  protected readonly answerBody = signal('');
  protected readonly outOfScopeReason = signal('');
  protected readonly confirmOutOfScope = signal(false);
  protected readonly confirmClose = signal(false);
  protected readonly busy = signal(false);
  protected readonly actionError = signal<ApiError | null>(null);

  protected select(question: MuseumQuestion): void {
    this.selectedId.set(question.id);
    this.answerBody.set('');
    this.outOfScopeReason.set('');
    this.confirmOutOfScope.set(false);
    this.confirmClose.set(false);
    this.actionError.set(null);
  }

  protected onStatusFilterChange(event: Event): void {
    this.statusFilter.set((event.target as HTMLSelectElement).value as MuseumQuestionStatus | '');
    this.currentPage.set(0);
    this.selectedId.set(null);
  }

  protected previousPage(): void {
    this.currentPage.update((page) => Math.max(0, page - 1));
  }

  protected nextPage(): void {
    this.currentPage.update((page) => Math.min(Math.max(0, this.totalPages() - 1), page + 1));
  }

  protected onTextInput(field: 'answer' | 'reason', event: Event): void {
    const value = (event.target as HTMLTextAreaElement).value;
    if (field === 'answer') this.answerBody.set(value);
    if (field === 'reason') this.outOfScopeReason.set(value);
  }

  protected async answer(question: MuseumQuestion): Promise<void> {
    const answerBody = this.answerBody().trim();
    if (!answerBody) return;
    await this.run(() => this.service.answer(question.id, { answerBody }));
    this.answerBody.set('');
  }

  protected async markOutOfScope(question: MuseumQuestion): Promise<void> {
    if (!this.confirmOutOfScope()) {
      this.confirmOutOfScope.set(true);
      return;
    }
    await this.run(() =>
      this.service.markOutOfScope(question.id, {
        reason: this.outOfScopeReason().trim() || null,
      }),
    );
    this.outOfScopeReason.set('');
    this.confirmOutOfScope.set(false);
  }

  protected async close(question: MuseumQuestion): Promise<void> {
    if (!this.confirmClose()) {
      this.confirmClose.set(true);
      return;
    }
    await this.run(() => this.service.close(question.id));
    this.confirmClose.set(false);
  }

  protected cancelConfirmations(): void {
    this.confirmOutOfScope.set(false);
    this.confirmClose.set(false);
  }

  protected statusLabel(status: MuseumQuestionStatus): string {
    return STATUS_LABELS[status];
  }

  protected formatDate(value: string | null): string {
    if (!value) return '—';
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: 'medium',
      timeStyle: 'short',
    }).format(new Date(value));
  }

  private async run(operation: () => Observable<unknown>): Promise<void> {
    this.busy.set(true);
    this.actionError.set(null);
    try {
      await firstValueFrom(operation());
      this.refreshToken.update((value) => value + 1);
    } catch (err) {
      this.actionError.set(toApiError(err));
    } finally {
      this.busy.set(false);
    }
  }
}
