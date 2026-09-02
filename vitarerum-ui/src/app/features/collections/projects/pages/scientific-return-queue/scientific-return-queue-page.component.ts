import { DatePipe } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  resource,
  signal,
} from '@angular/core';
import { RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { IDENTITY_SERVICE } from '@core/auth/identity.service';
import { ApiError, toApiError } from '@core/http/api-error.model';
import { EmptyStateComponent } from '@shared/components/empty-state/empty-state.component';
import { ErrorMessageComponent } from '@shared/components/error-message/error-message.component';
import {
  FiltersBarComponent,
  FiltersBarSelect,
  FiltersBarSelectChange,
} from '@shared/components/filters-bar/filters-bar.component';
import { LoadingStateComponent } from '@shared/components/loading-state/loading-state.component';
import { PageHeaderComponent } from '@shared/components/page-header/page-header.component';
import { PaginationComponent } from '@shared/components/pagination/pagination.component';

import { CandidateEvidenceListComponent } from '../../components/candidate-evidence-list/candidate-evidence-list.component';

import {
  ScientificReturnCandidateStatus,
  ScientificReturnEvidenceStrength,
  ScientificReturnReviewItem,
  InventoryEvidenceStatus,
} from '../../models/scientific-return.model';
import { ScientificReturnApiService } from '../../services/scientific-return-api.service';
import { projectDetailRouteForGroup } from '../../utils/project-detail-route.util';

type StatusFilter = ScientificReturnCandidateStatus | 'ALL';
type StrengthFilter = 'ALL' | 'PRIMARY' | 'SUPPORTING' | 'WEAK';
type SourceFilter = 'ALL' | 'CROSSREF' | 'OPENALEX' | 'EUROPE_PMC';

const PAGE_SIZE = 20;

@Component({
  selector: 'app-scientific-return-queue-page',
  standalone: true,
  imports: [
    CandidateEvidenceListComponent,
    DatePipe,
    RouterLink,
    EmptyStateComponent,
    ErrorMessageComponent,
    FiltersBarComponent,
    LoadingStateComponent,
    PageHeaderComponent,
    PaginationComponent,
  ],
  templateUrl: './scientific-return-queue-page.component.html',
  styleUrl: './scientific-return-queue-page.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ScientificReturnQueuePageComponent {
  private readonly api = inject(ScientificReturnApiService);
  private readonly identity = inject(IDENTITY_SERVICE);

  protected readonly status = signal<StatusFilter>('PENDING');
  protected readonly strength = signal<StrengthFilter>('ALL');
  protected readonly source = signal<SourceFilter>('ALL');
  protected readonly page = signal(0);
  protected readonly pageSize = PAGE_SIZE;

  protected readonly queueResource = resource({
    params: () => ({
      permissionId: this.identity.getPermissionId(),
      status: this.status(),
      strength: this.strength(),
      source: this.source(),
      page: this.page(),
    }),
    loader: ({ params }) =>
      firstValueFrom(
        this.api.listReviewQueue({
          status: params.status === 'ALL' ? null : params.status,
          evidenceStrength: params.strength === 'ALL' ? null : params.strength,
          source: params.source === 'ALL' ? null : params.source,
          page: params.page,
          size: PAGE_SIZE,
        }),
      ),
  });

  protected readonly queuePage = computed(() =>
    this.queueResource.hasValue() ? this.queueResource.value() : null,
  );
  protected readonly candidates = computed(() => this.queuePage()?.content ?? []);
  protected readonly total = computed(() => this.queuePage()?.totalElements ?? 0);
  protected readonly isRefreshing = computed(() => this.queueResource.isLoading());
  protected readonly totalPages = computed(() => this.queuePage()?.totalPages ?? 0);
  protected readonly activeFilterCount = computed(
    () =>
      Number(this.status() !== 'ALL') +
      Number(this.strength() !== 'ALL') +
      Number(this.source() !== 'ALL'),
  );
  protected readonly filterSelects = computed<readonly FiltersBarSelect[]>(() => [
    {
      key: 'status',
      label: 'Status',
      value: this.status(),
      options: [
        { value: 'PENDING', label: 'Pending' },
        { value: 'CONFIRMED', label: 'Confirmed' },
        { value: 'DISMISSED', label: 'Dismissed' },
        { value: 'ALL', label: 'All statuses' },
      ],
    },
    {
      key: 'strength',
      label: 'Evidence',
      value: this.strength(),
      options: [
        { value: 'ALL', label: 'All strengths' },
        { value: 'PRIMARY', label: 'Primary' },
        { value: 'SUPPORTING', label: 'Supporting' },
        { value: 'WEAK', label: 'Weak' },
      ],
    },
    {
      key: 'source',
      label: 'Source',
      value: this.source(),
      options: [
        { value: 'ALL', label: 'All sources' },
        { value: 'CROSSREF', label: 'Crossref' },
        { value: 'OPENALEX', label: 'OpenAlex' },
        { value: 'EUROPE_PMC', label: 'Europe PMC' },
      ],
    },
  ]);
  protected readonly queueError = computed<ApiError | null>(() => {
    const error = this.queueResource.error();
    return error ? toApiError(error) : null;
  });

  protected detailRoute(projectId: string): readonly string[] {
    return projectDetailRouteForGroup(projectId, this.identity.session()?.group);
  }

  protected filterLabel(value: string): string {
    const label = value.toLowerCase().replaceAll('_', ' ');
    return label.charAt(0).toUpperCase() + label.slice(1);
  }

  protected sourceLabel(source: string): string {
    if (source === 'EUROPE_PMC') return 'Europe PMC';
    if (source === 'OPENALEX') return 'OpenAlex';
    return this.filterLabel(source);
  }

  protected doiUrl(doi: string): string {
    return `https://doi.org/${doi.replace(/^https?:\/\/(?:dx\.)?doi\.org\//i, '')}`;
  }

  protected evidenceCount(
    candidate: ScientificReturnReviewItem,
    strength: ScientificReturnEvidenceStrength,
  ): number {
    return candidate.evidences.filter((evidence) => evidence.strength === strength).length;
  }

  protected inventoryEvidenceTitle(status: InventoryEvidenceStatus): string {
    switch (status) {
      case 'VERIFIED':
        return 'Inventory number observed in publication';
      case 'NOT_OBSERVED':
        return 'Publication text inspected; inventory number not found';
      case 'UNAVAILABLE':
        return 'Source did not provide inspectable inventory text';
    }
  }

  protected discoveryLabel(candidate: ScientificReturnReviewItem): string {
    return this.filterLabel(
      candidate.searchStrategy ?? candidate.discoveryBasis ?? 'Agentic search',
    );
  }

  protected refreshAll(): void {
    if (this.isRefreshing()) return;
    this.queueResource.reload();
  }

  protected clearFilters(): void {
    this.status.set('ALL');
    this.strength.set('ALL');
    this.source.set('ALL');
    this.page.set(0);
  }

  protected applyFilter(change: FiltersBarSelectChange): void {
    if (change.key === 'status') this.status.set(change.value as StatusFilter);
    else if (change.key === 'strength') this.strength.set(change.value as StrengthFilter);
    else this.source.set(change.value as SourceFilter);
    this.page.set(0);
  }

  protected previousPage(): void {
    this.page.update((value) => Math.max(0, value - 1));
  }

  protected nextPage(): void {
    this.page.update((value) => Math.min(Math.max(0, this.totalPages() - 1), value + 1));
  }
}
