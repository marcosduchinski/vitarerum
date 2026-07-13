import { ChangeDetectionStrategy, Component, input, output } from '@angular/core';

import { ApiError } from '@core/http/api-error.model';
import { CollectionObjectsSectionComponent } from '../../../shared/components/collection-objects-section/collection-objects-section.component';
import { AddProjectObjectsRequest, CollectionUseProjectObject } from '../../models/project.model';

@Component({
  selector: 'app-project-objects-section',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CollectionObjectsSectionComponent],
  templateUrl: './project-objects-section.component.html',
})
export class ProjectObjectsSectionComponent {
  readonly objects = input.required<readonly CollectionUseProjectObject[]>();
  readonly canManage = input(false);
  readonly adding = input(false);
  readonly removingId = input<string | null>(null);
  readonly addError = input<ApiError | null>(null);
  readonly removeError = input<ApiError | null>(null);

  readonly addRequested = output<AddProjectObjectsRequest>();
  readonly removeRequested = output<string>();
}
