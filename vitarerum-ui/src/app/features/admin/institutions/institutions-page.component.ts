import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  resource,
  signal,
} from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { MenuItem } from 'primeng/api';
import { ButtonDirective } from 'primeng/button';
import { toApiError } from '@core/http/api-error.model';
import { INSTITUTION_MANAGEMENT_SERVICE } from '@features/admin/services/institution-management.service';
import { Institution } from '@core/auth/models/institution.model';
import { Page } from '@shared/models/page.model';
import { DataTableComponent } from '@shared/components/data-table/data-table.component';
import { ErrorMessageComponent } from '@shared/components/error-message/error-message.component';
import { LoadingStateComponent } from '@shared/components/loading-state/loading-state.component';
import { EmptyStateComponent } from '@shared/components/empty-state/empty-state.component';
import { PageHeaderComponent } from '@shared/components/page-header/page-header.component';
import { PaginationComponent } from '@shared/components/pagination/pagination.component';
import { RowActionsComponent } from '@shared/components/row-actions/row-actions.component';

const PAGE_SIZE = 20;

@Component({
  selector: 'app-institutions-page',
  standalone: true,
  imports: [
    RouterLink,
    RowActionsComponent,
    ButtonDirective,
    DataTableComponent,
    ErrorMessageComponent,
    LoadingStateComponent,
    EmptyStateComponent,
    PageHeaderComponent,
    PaginationComponent,
  ],
  templateUrl: './institutions-page.component.html',
  styleUrl: './institutions-page.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class InstitutionsPageComponent {
  private readonly institutionService = inject(INSTITUTION_MANAGEMENT_SERVICE);
  private readonly router = inject(Router);

  protected readonly currentPage = signal(0);

  protected readonly institutionsResource = resource<Page<Institution>, { page: number; size: number }>({
    params: () => ({ page: this.currentPage(), size: PAGE_SIZE }),
    loader: ({ params }): Promise<Page<Institution>> =>
      firstValueFrom(this.institutionService.listInstitutions(params)),
  });

  protected readonly apiError = computed(() => {
    const err = this.institutionsResource.error();
    return err ? toApiError(err) : null;
  });

  protected readonly institutions = computed(
    () => this.institutionsResource.value()?.content ?? [],
  );
  protected readonly total = computed(
    () => this.institutionsResource.value()?.totalElements ?? 0,
  );
  protected readonly totalPages = computed(
    () => this.institutionsResource.value()?.totalPages ?? 0,
  );
  protected readonly pageSize = PAGE_SIZE;

  protected actionItemsFor(institution: Institution): MenuItem[] {
    return [
      {
        label: 'Details',
        icon: 'pi pi-eye',
        command: () => {
          void this.router.navigate(['/p/admin/institutions', institution.id]);
        },
      },
    ];
  }

  protected createInstitution(): void {
    void this.router.navigate(['/p/admin/institutions/new']);
  }

  protected prevPage(): void {
    this.currentPage.update(p => Math.max(0, p - 1));
  }

  protected nextPage(): void {
    this.currentPage.update(p => Math.min(Math.max(0, this.totalPages() - 1), p + 1));
  }
}
