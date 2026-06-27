import {
  ChangeDetectionStrategy,
  Component,
  computed,
  effect,
  inject,
  input,
  resource,
  signal,
} from '@angular/core';
import { FormField, form, validate } from '@angular/forms/signals';
import { Router, RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { ApiError, toApiError } from '@core/http/api-error.model';
import { ErrorMessageComponent } from '@shared/components/error-message/error-message.component';
import { LoadingStateComponent } from '@shared/components/loading-state/loading-state.component';
import {
  StatusChipComponent,
  WorkflowStatus,
} from '@shared/components/status-chip/status-chip.component';
import { IntendedUse, UseType } from '@shared/models/collection-use-status.model';

import { UpdateProposalRequest } from '../../models/proposal-actions.model';
import { ProposalDetail } from '../../models/proposal.model';
import { PROPOSAL_API_SERVICE } from '../../services/proposal-api.service';

interface ProposalEditFormModel {
  readonly title: string;
  readonly useType: UseType | '';
  readonly intendedUseDescription: string;
  readonly beginDate: string;
  readonly endDate: string;
}

interface ProposalEditSnapshot {
  readonly title: string | null;
  readonly intendedUse: IntendedUse | null;
  readonly beginDate: string | null;
  readonly endDate: string | null;
}

const EMPTY_FORM: ProposalEditFormModel = {
  title: '',
  useType: '',
  intendedUseDescription: '',
  beginDate: '',
  endDate: '',
};

@Component({
  selector: 'app-proposal-edit-page',
  standalone: true,
  imports: [
    RouterLink,
    FormField,
    LoadingStateComponent,
    ErrorMessageComponent,
    StatusChipComponent,
  ],
  templateUrl: './proposal-edit-page.component.html',
  styleUrl: './proposal-edit-page.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ProposalEditPageComponent {
  private readonly proposalService = inject(PROPOSAL_API_SERVICE);
  private readonly router = inject(Router);
  private loadedProposalId: string | null = null;

  readonly id = input.required<string>();

  protected readonly proposalResource = resource({
    params: () => this.id(),
    loader: ({ params }) => firstValueFrom(this.proposalService.getProposal(params)),
  });
  protected readonly proposal = computed(() => this.proposalResource.value() ?? null);
  protected readonly loadError = computed<ApiError | null>(() => {
    const error = this.proposalResource.error();
    return error ? toApiError(error) : null;
  });
  protected readonly pending = signal(false);
  protected readonly updateError = signal<ApiError | null>(null);
  protected readonly formModel = signal<ProposalEditFormModel>({ ...EMPTY_FORM });
  protected readonly original = signal<ProposalEditSnapshot | null>(null);

  // Signal Forms is experimental in Angular 21. It is kept local to this
  // route-level editor so future API changes have a contained migration surface.
  protected readonly editForm = form(this.formModel, (path) => {
    validate(path.useType, ({ value, valueOf }) => {
      const description = valueOf(path.intendedUseDescription).trim();
      return description && !value()
        ? { kind: 'missing-use-type', message: 'Select an intended-use type.' }
        : undefined;
    });
    validate(path.endDate, ({ value, valueOf }) => {
      const beginDate = valueOf(path.beginDate);
      const endDate = value();
      return beginDate && endDate && endDate < beginDate
        ? { kind: 'date-range', message: 'End date cannot precede begin date.' }
        : undefined;
    });
  });

  protected readonly canEdit = computed(() => {
    const status = this.proposal()?.status;
    return status === 'SUBMITTED' || status === 'PENDING';
  });
  protected readonly changed = computed(() => {
    const original = this.original();
    return original ? !this.snapshotsEqual(original, this.currentSnapshot()) : false;
  });
  protected readonly saveDisabled = computed(
    () =>
      this.pending() ||
      !this.proposal() ||
      !this.canEdit() ||
      !this.changed() ||
      this.editForm().invalid(),
  );

  private readonly syncForm = effect(() => {
    const proposal = this.proposal();
    if (!proposal || this.loadedProposalId === proposal.id) return;

    this.loadedProposalId = proposal.id;
    const snapshot = this.snapshotFromProposal(proposal);
    this.original.set(snapshot);
    this.formModel.set({
      title: snapshot.title ?? '',
      useType: snapshot.intendedUse?.useType ?? '',
      intendedUseDescription: snapshot.intendedUse?.description ?? '',
      beginDate: snapshot.beginDate ?? '',
      endDate: snapshot.endDate ?? '',
    });
    this.updateError.set(null);
  });

  protected asWorkflowStatus(value: string): WorkflowStatus {
    return value as WorkflowStatus;
  }

  protected async save(event: Event): Promise<void> {
    event.preventDefault();
    this.editForm().markAsTouched();
    if (this.saveDisabled()) return;

    const request = this.buildRequest();
    if (!Object.keys(request).length) return;

    this.pending.set(true);
    this.updateError.set(null);
    try {
      await firstValueFrom(this.proposalService.updateProposal(this.id(), request));
      await this.navigateToDetail();
    } catch (error) {
      this.updateError.set(toApiError(error));
    } finally {
      this.pending.set(false);
    }
  }

  protected cancel(): void {
    if (this.pending()) return;
    void this.navigateToDetail();
  }

  private buildRequest(): UpdateProposalRequest {
    const original = this.original();
    if (!original) return {};

    const current = this.currentSnapshot();
    const request: {
      title?: string | null;
      intendedUse?: IntendedUse;
      beginDate?: string | null;
      endDate?: string | null;
    } = {};

    if (current.title !== original.title) request.title = current.title;
    if (!this.intendedUsesEqual(current.intendedUse, original.intendedUse) && current.intendedUse) {
      request.intendedUse = current.intendedUse;
    }
    if (current.beginDate !== original.beginDate) request.beginDate = current.beginDate;
    if (current.endDate !== original.endDate) request.endDate = current.endDate;

    return request;
  }

  private currentSnapshot(): ProposalEditSnapshot {
    const value = this.formModel();
    return {
      title: value.title.trim() || null,
      intendedUse: value.useType
        ? { useType: value.useType, description: value.intendedUseDescription.trim() }
        : null,
      beginDate: value.beginDate || null,
      endDate: value.endDate || null,
    };
  }

  private snapshotFromProposal(proposal: ProposalDetail): ProposalEditSnapshot {
    return {
      title: proposal.title?.trim() || null,
      intendedUse: proposal.intendedUse
        ? {
            useType: proposal.intendedUse.useType,
            description: proposal.intendedUse.description.trim(),
          }
        : null,
      beginDate: proposal.beginDate ?? null,
      endDate: proposal.endDate ?? null,
    };
  }

  private snapshotsEqual(a: ProposalEditSnapshot, b: ProposalEditSnapshot): boolean {
    return (
      a.title === b.title &&
      this.intendedUsesEqual(a.intendedUse, b.intendedUse) &&
      a.beginDate === b.beginDate &&
      a.endDate === b.endDate
    );
  }

  private intendedUsesEqual(a: IntendedUse | null, b: IntendedUse | null): boolean {
    return a?.useType === b?.useType && a?.description === b?.description;
  }

  private navigateToDetail(): Promise<boolean> {
    return this.router.navigate(['/p/collections/proposals/my-assignments', this.id()]);
  }
}
