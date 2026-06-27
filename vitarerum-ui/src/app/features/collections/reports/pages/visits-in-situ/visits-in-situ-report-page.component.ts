import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  resource,
  signal,
} from '@angular/core';
import { Router } from '@angular/router';
import { MenuItem } from 'primeng/api';
import { firstValueFrom } from 'rxjs';

import { ApiError, toApiError } from '@core/http/api-error.model';
import { EmptyStateComponent } from '@shared/components/empty-state/empty-state.component';
import { ErrorMessageComponent } from '@shared/components/error-message/error-message.component';
import { LoadingStateComponent } from '@shared/components/loading-state/loading-state.component';
import { PageHeaderComponent } from '@shared/components/page-header/page-header.component';
import { RowActionsComponent } from '@shared/components/row-actions/row-actions.component';

import { InSituVisitReportListItem } from '../../models/report.model';
import { REPORTS_API_SERVICE } from '../../services/reports-api.service';

const DEFAULT_PAGE_SIZE = 20;
const PAGE_SIZE_OPTIONS = [10, 20, 50, 100] as const;

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

function formatDate(iso: string): string {
  try {
    return new Date(`${iso}T00:00:00`).toLocaleDateString('en-GB', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
    });
  } catch {
    return iso;
  }
}

@Component({
  selector: 'app-visits-in-situ-report-page',
  standalone: true,
  imports: [
    RowActionsComponent,
    PageHeaderComponent,
    LoadingStateComponent,
    ErrorMessageComponent,
    EmptyStateComponent,
  ],
  templateUrl: './visits-in-situ-report-page.component.html',
  styleUrl: './visits-in-situ-report-page.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class VisitsInSituReportPageComponent {
  private readonly reportsService = inject(REPORTS_API_SERVICE);
  private readonly router = inject(Router);

  protected readonly currentPage = signal(0);
  protected readonly pageSize = signal(DEFAULT_PAGE_SIZE);

  protected readonly reportResource = resource({
    params: () => ({ page: this.currentPage(), size: this.pageSize() }),
    loader: ({ params }) => firstValueFrom(this.reportsService.listInSituVisitReports(params)),
  });

  protected readonly rows = computed(() => this.reportResource.value()?.content ?? []);
  protected readonly totalRows = computed(() => this.reportResource.value()?.totalElements ?? 0);
  protected readonly totalPages = computed(() => this.reportResource.value()?.totalPages ?? 0);
  protected readonly rangeStart = computed(() =>
    this.totalRows() === 0 ? 0 : this.currentPage() * this.pageSize() + 1,
  );
  protected readonly rangeEnd = computed(() =>
    Math.min((this.currentPage() + 1) * this.pageSize(), this.totalRows()),
  );
  protected readonly listError = computed<ApiError | null>(() => {
    const err = this.reportResource.error();
    return err ? toApiError(err) : null;
  });

  protected readonly pageSizeOptions = PAGE_SIZE_OPTIONS;
  protected readonly formatDateTime = formatDateTime;

  protected actionItemsFor(report: InSituVisitReportListItem): MenuItem[] {
    return [
      {
        label: 'Details',
        icon: 'pi pi-eye',
        command: () => {
          void this.router.navigate([
            '/p/collections/reports/visits-in-situ',
            report.projectId,
            report.id,
          ]);
        },
      },
    ];
  }

  protected valueOrUnavailable(value: string | null): string {
    return value?.trim() || 'Unavailable';
  }

  protected visitPeriod(report: InSituVisitReportListItem): string {
    const begin = report.visitBeginDate;
    const end = report.visitEndDate;
    if (!begin && !end) return 'Unavailable';
    if (!begin) return `Until ${formatDate(end!)}`;
    if (!end) return `From ${formatDate(begin)}`;
    return `${formatDate(begin)} — ${formatDate(end)}`;
  }

  protected firstPage(): void {
    this.currentPage.set(0);
  }

  protected prevPage(): void {
    this.currentPage.update((page) => Math.max(0, page - 1));
  }

  protected nextPage(): void {
    this.currentPage.update((page) => Math.min(Math.max(0, this.totalPages() - 1), page + 1));
  }

  protected lastPage(): void {
    this.currentPage.set(Math.max(0, this.totalPages() - 1));
  }

  protected onPageSizeChange(event: Event): void {
    this.pageSize.set(Number((event.target as HTMLSelectElement).value));
    this.currentPage.set(0);
  }
}
