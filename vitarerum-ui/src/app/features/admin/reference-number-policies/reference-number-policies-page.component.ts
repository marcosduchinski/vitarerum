import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  resource,
  signal,
} from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { ApiError, toApiError } from '@core/http/api-error.model';
import { ErrorMessageComponent } from '@shared/components/error-message/error-message.component';
import { LoadingStateComponent } from '@shared/components/loading-state/loading-state.component';
import { PageHeaderComponent } from '@shared/components/page-header/page-header.component';

import {
  ReferenceKind,
  ReferencePolicy,
  ReferencePolicyPreview,
  ReferencePolicyStatus,
} from '../models/reference-number-policy.model';
import { REFERENCE_NUMBER_POLICY_SERVICE } from '../services/reference-number-policy.service';

const KIND_OPTIONS: readonly { readonly value: ReferenceKind; readonly label: string }[] = [
  { value: 'PROPOSAL', label: 'Proposals' },
  { value: 'COLLECTION_USE_PROJECT', label: 'Projects' },
  { value: 'OBJECT_ACCESS_LOG', label: 'Object access logs' },
  { value: 'OBJECT_OCCURRENCE_LOG', label: 'Object occurrence logs' },
  { value: 'PUBLICATION_LOG', label: 'Publication logs' },
];

const STATUS_ORDER: Record<ReferencePolicyStatus, number> = {
  ACTIVE: 0,
  DRAFT: 1,
  INACTIVE: 2,
  RETIRED: 3,
};

interface PolicyGroup {
  readonly kind: ReferenceKind;
  readonly label: string;
  readonly policies: readonly ReferencePolicy[];
}

@Component({
  selector: 'app-reference-number-policies-page',
  standalone: true,
  imports: [PageHeaderComponent, ErrorMessageComponent, LoadingStateComponent],
  templateUrl: './reference-number-policies-page.component.html',
  styleUrl: './reference-number-policies-page.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ReferenceNumberPoliciesPageComponent {
  private readonly service = inject(REFERENCE_NUMBER_POLICY_SERVICE);

  protected readonly kindOptions = KIND_OPTIONS;
  protected readonly selectedKind = signal<ReferenceKind>('PROPOSAL');
  protected readonly newMask = signal(defaultMask('PROPOSAL'));
  protected readonly sampleDate = signal(new Date().toISOString().slice(0, 10));
  protected readonly preview = signal<ReferencePolicyPreview | null>(null);
  protected readonly actionError = signal<ApiError | null>(null);
  protected readonly busy = signal(false);

  protected readonly policiesResource = resource({
    loader: () => firstValueFrom(this.service.list()),
  });

  protected readonly loading = computed(() => this.policiesResource.isLoading());
  protected readonly loadError = computed<ApiError | null>(() => {
    const err = this.policiesResource.error();
    return err ? toApiError(err) : null;
  });

  protected readonly groups = computed<readonly PolicyGroup[]>(() => {
    const policies = this.policiesResource.value() ?? [];
    return KIND_OPTIONS.map((option) => ({
      kind: option.value,
      label: option.label,
      policies: policies
        .filter((policy) => policy.kind === option.value)
        .sort(
          (a, b) =>
            STATUS_ORDER[a.status] - STATUS_ORDER[b.status] ||
            b.createdAt.localeCompare(a.createdAt),
        ),
    }));
  });

  protected readonly canSubmit = computed(
    () => !this.busy() && this.newMask().trim().length > 0 && this.sampleDate().length > 0,
  );

  protected setKind(event: Event): void {
    const kind = (event.target as HTMLSelectElement).value as ReferenceKind;
    this.selectedKind.set(kind);
    this.newMask.set(defaultMask(kind));
    this.preview.set(null);
    this.actionError.set(null);
  }

  protected async previewMask(): Promise<void> {
    const mask = this.newMask().trim();
    if (!mask) return;
    await this.run(async () => {
      const preview = await firstValueFrom(
        this.service.preview({
          kind: this.selectedKind(),
          mask,
          sampleDate: this.sampleDate(),
        }),
      );
      this.preview.set(preview);
    });
  }

  protected async createDraft(): Promise<void> {
    const mask = this.newMask().trim();
    if (!mask) return;
    await this.run(async () => {
      await firstValueFrom(this.service.create({ kind: this.selectedKind(), mask }));
      this.preview.set(null);
      this.policiesResource.reload();
    });
  }

  protected async activate(policy: ReferencePolicy): Promise<void> {
    await this.run(async () => {
      await firstValueFrom(this.service.activate(policy.id));
      this.policiesResource.reload();
    });
  }

  protected async deactivate(policy: ReferencePolicy): Promise<void> {
    await this.run(async () => {
      await firstValueFrom(this.service.deactivate(policy.id));
      this.policiesResource.reload();
    });
  }

  protected kindLabel(kind: ReferenceKind): string {
    return KIND_OPTIONS.find((option) => option.value === kind)?.label ?? kind;
  }

  protected statusLabel(status: ReferencePolicyStatus): string {
    return status.charAt(0) + status.slice(1).toLowerCase();
  }

  protected formatDate(iso: string | null): string {
    if (!iso) return 'Not set';
    return new Intl.DateTimeFormat('en-GB', {
      dateStyle: 'medium',
      timeStyle: 'short',
    }).format(new Date(iso));
  }

  private async run(operation: () => Promise<unknown>): Promise<void> {
    this.busy.set(true);
    this.actionError.set(null);
    try {
      await operation();
    } catch (err) {
      this.actionError.set(toApiError(err));
    } finally {
      this.busy.set(false);
    }
  }
}

function defaultMask(kind: ReferenceKind): string {
  switch (kind) {
    case 'PROPOSAL':
      return 'VRP-YYYYMMDD-XXXX';
    case 'COLLECTION_USE_PROJECT':
      return 'CUP-XXXXXXXX';
    case 'OBJECT_ACCESS_LOG':
      return 'OAL-XXXXXXXX';
    case 'OBJECT_OCCURRENCE_LOG':
      return 'OOL-XXXXXXXX';
    case 'PUBLICATION_LOG':
      return 'PUB-XXXXXXXX';
  }
}
