import { DatePipe } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  resource,
  signal,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { firstValueFrom } from 'rxjs';

import { ApiError, toApiError } from '@core/http/api-error.model';
import { EmptyStateComponent } from '@shared/components/empty-state/empty-state.component';
import { ErrorMessageComponent } from '@shared/components/error-message/error-message.component';
import { LoadingStateComponent } from '@shared/components/loading-state/loading-state.component';
import { PageHeaderComponent } from '@shared/components/page-header/page-header.component';

import {
  ExternalPublication,
  ExternalPublicationProfile,
  ExternalPublicationResourceType,
  ExternalPublicationStatus,
  PublishableResource,
} from '../models/external-publication.model';
import { EXTERNAL_PUBLICATION_SERVICE } from '../services/external-publication.service';

const PAGE_SIZE = 20;

const RESOURCE_TYPES: readonly {
  readonly value: ExternalPublicationResourceType;
  readonly label: string;
}[] = [
  { value: 'PROPOSAL', label: 'Proposal' },
  { value: 'PROJECT', label: 'Project' },
  { value: 'IN_SITU_VISIT_REPORT', label: 'In-situ report' },
];

const PROFILES: readonly { readonly value: ExternalPublicationProfile; readonly label: string }[] =
  [
    { value: 'SUMMARY', label: 'Summary' },
    { value: 'DETAIL', label: 'Detail' },
    { value: 'JSON_LD', label: 'JSON-LD' },
  ];

@Component({
  selector: 'app-external-publications-page',
  standalone: true,
  imports: [
    FormsModule,
    DatePipe,
    PageHeaderComponent,
    ErrorMessageComponent,
    LoadingStateComponent,
    EmptyStateComponent,
  ],
  templateUrl: './external-publications-page.component.html',
  styleUrl: './external-publications-page.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ExternalPublicationsPageComponent {
  private readonly service = inject(EXTERNAL_PUBLICATION_SERVICE);

  protected readonly resourceTypes = RESOURCE_TYPES;
  protected readonly profiles = PROFILES;
  protected readonly statusOptions: readonly ExternalPublicationStatus[] = ['PUBLISHED', 'REVOKED'];

  protected readonly q = signal('');
  protected readonly resourceType = signal<ExternalPublicationResourceType | ''>('');
  protected readonly status = signal<ExternalPublicationStatus | ''>('');
  protected readonly profile = signal<ExternalPublicationProfile | ''>('');
  protected readonly currentPage = signal(0);

  protected readonly createDrawerOpen = signal(false);
  protected readonly createStep = signal<1 | 2 | 3 | 4>(1);
  protected readonly createType = signal<ExternalPublicationResourceType>('PROJECT');
  protected readonly createProfile = signal<ExternalPublicationProfile>('DETAIL');
  protected readonly createExpiresAt = signal('');
  protected readonly resourceQuery = signal('');
  protected readonly selectedResource = signal<PublishableResource | null>(null);
  protected readonly latestUrl = signal<string | null>(null);
  protected readonly actionError = signal<ApiError | null>(null);
  protected readonly busy = signal(false);

  protected readonly publicationsResource = resource({
    params: () => ({
      page: this.currentPage(),
      size: PAGE_SIZE,
      q: this.q(),
      resourceType: this.resourceType() || null,
      status: this.status() || null,
      profile: this.profile() || null,
    }),
    loader: ({ params }) => firstValueFrom(this.service.listPublications(params)),
  });

  protected readonly publishableResource = resource({
    params: () => ({
      page: 0,
      size: 10,
      resourceType: this.createType(),
      q: this.resourceQuery(),
    }),
    loader: ({ params }) => firstValueFrom(this.service.listPublishableResources(params)),
  });

  protected readonly publications = computed(
    () => this.publicationsResource.value()?.content ?? [],
  );
  protected readonly total = computed(() => this.publicationsResource.value()?.totalElements ?? 0);
  protected readonly publishedCount = computed(
    () => this.publications().filter((item) => item.status === 'PUBLISHED').length,
  );
  protected readonly revokedCount = computed(
    () => this.publications().filter((item) => item.status === 'REVOKED').length,
  );
  protected readonly expiringCount = computed(
    () =>
      this.publications().filter((item) => item.status === 'PUBLISHED' && item.expiresAt).length,
  );
  protected readonly totalPages = computed(
    () => this.publicationsResource.value()?.totalPages ?? 0,
  );
  protected readonly publishableResources = computed(
    () => this.publishableResource.value()?.content ?? [],
  );
  protected readonly loadError = computed<ApiError | null>(() => {
    const err = this.publicationsResource.error();
    return err ? toApiError(err) : null;
  });
  protected readonly pickerError = computed<ApiError | null>(() => {
    const err = this.publishableResource.error();
    return err ? toApiError(err) : null;
  });
  protected readonly canCreate = computed(
    () => !this.busy() && this.selectedResource() !== null && this.createProfileAllowed(),
  );

  protected readonly canReviewPublication = computed(
    () => this.selectedResource() !== null && this.createProfileAllowed(),
  );

  protected openCreateDrawer(): void {
    this.createDrawerOpen.set(true);
    this.createStep.set(1);
    this.latestUrl.set(null);
  }

  protected closeCreateDrawer(): void {
    this.createDrawerOpen.set(false);
  }

  protected goToCreateStep(step: 1 | 2 | 3 | 4): void {
    this.createStep.set(step);
  }

  protected setFilterType(value: string): void {
    this.resourceType.set(value as ExternalPublicationResourceType | '');
    this.currentPage.set(0);
  }

  protected setFilterStatus(value: string): void {
    this.status.set(value as ExternalPublicationStatus | '');
    this.currentPage.set(0);
  }

  protected setFilterProfile(value: string): void {
    this.profile.set(value as ExternalPublicationProfile | '');
    this.currentPage.set(0);
  }

  protected setCreateType(value: ExternalPublicationResourceType): void {
    this.createType.set(value);
    this.selectedResource.set(null);
    this.latestUrl.set(null);
    if (value !== 'IN_SITU_VISIT_REPORT' && this.createProfile() === 'JSON_LD') {
      this.createProfile.set('DETAIL');
    }
    this.publishableResource.reload();
  }

  protected selectResource(resource: PublishableResource): void {
    this.selectedResource.set(resource);
    this.latestUrl.set(null);
  }

  protected async createPublication(): Promise<void> {
    const resource = this.selectedResource();
    if (!resource || !this.createProfileAllowed()) return;
    const expiresAt = this.toIsoInstant(this.createExpiresAt());
    await this.run(async () => {
      const created = await firstValueFrom(
        this.service.createPublication({
          resourceType: this.createType(),
          resourceId: resource.id,
          accessMode: 'TOKEN',
          profile: this.createProfile(),
          expiresAt,
        }),
      );
      this.latestUrl.set(created.url);
      this.selectedResource.set(null);
      this.createStep.set(4);
      this.publicationsResource.reload();
    });
  }

  protected async revoke(publication: ExternalPublication): Promise<void> {
    await this.run(async () => {
      await firstValueFrom(this.service.revokePublication(publication.id));
      this.publicationsResource.reload();
    });
  }

  protected async copyUrl(publication: ExternalPublication): Promise<void> {
    if (!publication.url) return;
    await navigator.clipboard?.writeText(publication.url);
  }

  protected prevPage(): void {
    this.currentPage.update((page) => Math.max(0, page - 1));
  }

  protected nextPage(): void {
    this.currentPage.update((page) => Math.min(Math.max(0, this.totalPages() - 1), page + 1));
  }

  protected resourceTypeLabel(type: ExternalPublicationResourceType): string {
    return RESOURCE_TYPES.find((item) => item.value === type)?.label ?? type;
  }

  protected profileLabel(profile: ExternalPublicationProfile): string {
    return PROFILES.find((item) => item.value === profile)?.label ?? profile;
  }

  protected profileTone(profile: ExternalPublicationProfile): string {
    if (profile === 'SUMMARY') return 'Minimized';
    if (profile === 'JSON_LD') return 'Machine';
    return 'Complete';
  }

  protected createProfileAllowed(): boolean {
    return this.createProfile() !== 'JSON_LD' || this.createType() === 'IN_SITU_VISIT_REPORT';
  }

  private async run(action: () => Promise<void>): Promise<void> {
    this.busy.set(true);
    this.actionError.set(null);
    try {
      await action();
    } catch (error) {
      this.actionError.set(toApiError(error));
    } finally {
      this.busy.set(false);
    }
  }

  private toIsoInstant(value: string | null): string | null {
    if (!value) return null;
    return new Date(value).toISOString();
  }
}
