import { ChangeDetectionStrategy, Component, computed, input, output } from '@angular/core';

import { ApiError } from '@core/http/api-error.model';
import {
  CollectionObjectSectionItem,
  CollectionObjectsSectionComponent,
} from '../../../shared/components/collection-objects-section/collection-objects-section.component';
import { AddRequestedObjectsRequest } from '../../models/proposal-actions.model';
import { RequestedObject } from '../../models/proposal.model';

@Component({
  selector: 'app-proposal-objects-section',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CollectionObjectsSectionComponent],
  templateUrl: './proposal-objects-section.component.html',
})
export class ProposalObjectsSectionComponent {
  readonly objects = input.required<readonly RequestedObject[]>();
  readonly removingId = input<string | null>(null);
  readonly removeError = input<ApiError | null>(null);
  readonly addError = input<ApiError | null>(null);
  readonly adding = input(false);

  readonly removeRequested = output<string>();
  readonly addRequested = output<AddRequestedObjectsRequest>();

  protected readonly sectionObjects = computed<readonly CollectionObjectSectionItem[]>(() =>
    this.objects().map((object) => ({
      id: object.id,
      inventoryNumber: object.objectReference.inventoryNumber,
      displayTitle: object.objectReference.displayTitle,
      objectName: object.objectReference.objectName,
      briefDescriptionSnapshot: object.objectReference.briefDescriptionSnapshot,
      category: object.category,
      description: object.description,
      requestedAt: object.requestedAt,
    })),
  );
}
