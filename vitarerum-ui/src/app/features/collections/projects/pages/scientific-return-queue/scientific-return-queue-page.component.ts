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
import { LoadingStateComponent } from '@shared/components/loading-state/loading-state.component';
import { PageHeaderComponent } from '@shared/components/page-header/page-header.component';

import {
  ScientificReturnCandidateStatus,
  ScientificReturnEvidence,
} from '../../models/scientific-return.model';
import { ScientificReturnApiService } from '../../services/scientific-return-api.service';
import { projectDetailRouteForGroup } from '../../utils/project-detail-route.util';

type StatusFilter = ScientificReturnCandidateStatus | 'ALL';
type StrengthFilter = 'ALL' | 'PRIMARY' | 'SUPPORTING' | 'WEAK';
type SourceFilter = 'ALL' | 'CROSSREF' | 'OPENALEX';

@Component({
  selector: 'app-scientific-return-queue-page',
  standalone: true,
  imports: [
    DatePipe,
    RouterLink,
    EmptyStateComponent,
    ErrorMessageComponent,
    LoadingStateComponent,
    PageHeaderComponent,
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

  protected readonly metricsResource = resource({
    params: () => this.identity.getPermissionId(),
    loader: () => firstValueFrom(this.api.getMetrics()),
  });

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
          size: 20,
        }),
      ),
  });

  protected readonly candidates = computed(() => this.queueResource.value()?.content ?? []);
  protected readonly total = computed(() => this.queueResource.value()?.totalElements ?? 0);
  protected readonly totalPages = computed(() => this.queueResource.value()?.totalPages ?? 0);
  protected readonly queueError = computed<ApiError | null>(() => {
    const error = this.queueResource.error();
    return error ? toApiError(error) : null;
  });

  protected detailRoute(projectId: string): readonly string[] {
    return projectDetailRouteForGroup(projectId, this.identity.session()?.group);
  }

  protected evidenceLabel(evidence: ScientificReturnEvidence): string {
    return evidence.type.toLowerCase().replaceAll('_', ' ');
  }

  protected onStatus(event: Event): void {
    this.status.set((event.target as HTMLSelectElement).value as StatusFilter);
    this.page.set(0);
  }

  protected onStrength(event: Event): void {
    this.strength.set((event.target as HTMLSelectElement).value as StrengthFilter);
    this.page.set(0);
  }

  protected onSource(event: Event): void {
    this.source.set((event.target as HTMLSelectElement).value as SourceFilter);
    this.page.set(0);
  }

  protected previousPage(): void {
    this.page.update((value) => Math.max(0, value - 1));
  }

  protected nextPage(): void {
    this.page.update((value) => Math.min(Math.max(0, this.totalPages() - 1), value + 1));
  }
}
