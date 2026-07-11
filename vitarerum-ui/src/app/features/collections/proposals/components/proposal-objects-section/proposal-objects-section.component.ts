import { ChangeDetectionStrategy, Component, input, output, signal } from '@angular/core';

import { ApiError } from '@core/http/api-error.model';
import { ConfirmModalComponent } from '@shared/components/confirm-modal/confirm-modal.component';
import { ErrorMessageComponent } from '@shared/components/error-message/error-message.component';

import { RequestedObject } from '../../models/proposal.model';
import { formatProposalDetailDateTime } from '../../proposal-detail.presentation';

@Component({
  selector: 'app-proposal-objects-section',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ConfirmModalComponent, ErrorMessageComponent],
  templateUrl: './proposal-objects-section.component.html',
  styleUrl: './proposal-objects-section.component.scss',
})
export class ProposalObjectsSectionComponent {
  readonly objects = input.required<readonly RequestedObject[]>();
  readonly removingId = input<string | null>(null);
  readonly removeError = input<ApiError | null>(null);

  readonly removeRequested = output<string>();

  protected readonly addModalOpen = signal(false);
  protected readonly removeTargetId = signal<string | null>(null);

  protected formatDate(value: string): string {
    return formatProposalDetailDateTime(value);
  }

  protected readonly removeTargetName = () => {
    const targetId = this.removeTargetId();
    const target = this.objects().find((object) => object.id === targetId);
    return (
      target?.objectReference.displayTitle ??
      target?.objectReference.objectName ??
      target?.objectReference.inventoryNumber ??
      'this object'
    );
  };

  protected openAddModal(): void {
    this.addModalOpen.set(true);
  }

  protected closeAddModal(): void {
    this.addModalOpen.set(false);
  }

  protected requestRemove(objectId: string): void {
    if (this.removingId()) return;
    this.removeTargetId.set(objectId);
  }

  protected cancelRemove(): void {
    if (this.removingId()) return;
    this.removeTargetId.set(null);
  }

  protected confirmRemove(): void {
    const targetId = this.removeTargetId();
    if (!targetId || this.removingId()) return;
    this.removeRequested.emit(targetId);
    this.removeTargetId.set(null);
  }
}
