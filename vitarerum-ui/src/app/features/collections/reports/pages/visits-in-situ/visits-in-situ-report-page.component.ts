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

import {
  InSituVisitReportListItem,
  InSituVisitReportNarrativeType,
  InSituVisitReportsQuery,
} from '../../models/report.model';
import { REPORTS_API_SERVICE } from '../../services/reports-api.service';

const DEFAULT_PAGE_SIZE = 20;
const PAGE_SIZE_OPTIONS = [10, 20, 50, 100] as const;
const NARRATIVE_TYPE_OPTIONS = [
  { value: '', label: 'All types' },
  { value: 'institutional', label: 'Institutional' },
  { value: 'scientific', label: 'Scientific' },
  { value: 'audioguide_adult', label: 'Audioguide adult' },
  { value: 'audioguide_child', label: 'Audioguide child' },
  { value: 'social_media', label: 'Social media' },
] as const;
const TARGET_LANGUAGE_LABELS = [
  { value: '', label: 'All languages' },
  { value: 'pt', label: 'Portuguese' },
  { value: 'en', label: 'English' },
] as const;

interface ReportFilterDraft {
  readonly search: string;
  readonly generatedFrom: string;
  readonly generatedTo: string;
  readonly visitFrom: string;
  readonly visitTo: string;
  readonly narrativeType: InSituVisitReportNarrativeType | '';
}

type MutableReportFilters = {
  -readonly [K in keyof InSituVisitReportsQuery]?: InSituVisitReportsQuery[K];
};

const EMPTY_FILTERS: ReportFilterDraft = {
  search: '',
  generatedFrom: '',
  generatedTo: '',
  visitFrom: '',
  visitTo: '',
  narrativeType: '',
};

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
    RouterLink,
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
  protected readonly filterDraft = signal<ReportFilterDraft>(EMPTY_FILTERS);
  protected readonly appliedFilters = signal<ReportFilterDraft>(EMPTY_FILTERS);

  protected readonly reportResource = resource({
    params: () => ({
      page: this.currentPage(),
      size: this.pageSize(),
      ...this.toQueryFilters(this.appliedFilters()),
    }),
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
  protected readonly narrativeTypeOptions = NARRATIVE_TYPE_OPTIONS;
  protected readonly formatDateTime = formatDateTime;
  protected readonly hasAppliedFilters = computed(() => this.hasFilters(this.appliedFilters()));
  protected readonly activeFilterCount = computed(
    () => Object.values(this.appliedFilters()).filter((value) => value.trim() !== '').length,
  );

  protected actionItemsFor(report: InSituVisitReportListItem): MenuItem[] {
    return [
      {
        label: 'Audit trail',
        icon: 'pi pi-list-check',
        command: () => {
          void this.router.navigate([
            '/p/collections/reports/visits-in-situ',
            report.projectId,
            report.id,
            'audit-trail',
          ]);
        },
      },
    ];
  }

  protected valueOrUnavailable(value: string | null): string {
    return value?.trim() || 'Unavailable';
  }

  protected generationProfile(report: InSituVisitReportListItem): string {
    const parts = [
      this.narrativeTypeLabel(report.narrativeType),
      this.targetLanguageLabel(report.targetLanguage),
      report.creativityTemperature === null ? null : `T ${report.creativityTemperature}`,
    ].filter((part): part is string => Boolean(part));
    return parts.length ? parts.join(' · ') : 'Unavailable';
  }

  protected temperatureLabel(temperature: number | null): string | null {
    return temperature === null ? null : `T ${temperature}`;
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

  protected updateFilter(name: keyof ReportFilterDraft, event: Event): void {
    const value = (event.target as HTMLInputElement | HTMLSelectElement).value;
    this.filterDraft.update((filters) => ({ ...filters, [name]: value }) as ReportFilterDraft);
  }

  protected applyFilters(): void {
    this.appliedFilters.set(this.normalizedFilters(this.filterDraft()));
    this.currentPage.set(0);
  }

  protected clearFilters(): void {
    this.filterDraft.set(EMPTY_FILTERS);
    this.appliedFilters.set(EMPTY_FILTERS);
    this.currentPage.set(0);
  }

  private toQueryFilters(filters: ReportFilterDraft): Partial<InSituVisitReportsQuery> {
    const query: MutableReportFilters = {};
    if (filters.search) query.search = filters.search;
    if (filters.generatedFrom) query.generatedFrom = `${filters.generatedFrom}T00:00:00.000Z`;
    if (filters.generatedTo) query.generatedTo = `${filters.generatedTo}T23:59:59.999Z`;
    if (filters.visitFrom) query.visitFrom = filters.visitFrom;
    if (filters.visitTo) query.visitTo = filters.visitTo;
    if (filters.narrativeType) query.narrativeType = filters.narrativeType;
    return query;
  }

  private normalizedFilters(filters: ReportFilterDraft): ReportFilterDraft {
    return {
      search: filters.search.trim(),
      generatedFrom: filters.generatedFrom,
      generatedTo: filters.generatedTo,
      visitFrom: filters.visitFrom,
      visitTo: filters.visitTo,
      narrativeType: filters.narrativeType,
    };
  }

  private hasFilters(filters: ReportFilterDraft): boolean {
    return Object.values(filters).some((value) => value.trim() !== '');
  }

  protected narrativeTypeLabel(type: string | null): string | null {
    if (!type) return null;
    return NARRATIVE_TYPE_OPTIONS.find((option) => option.value === type)?.label ?? type;
  }

  protected targetLanguageLabel(language: string | null): string | null {
    if (!language) return null;
    return TARGET_LANGUAGE_LABELS.find((option) => option.value === language)?.label ?? language;
  }
}
