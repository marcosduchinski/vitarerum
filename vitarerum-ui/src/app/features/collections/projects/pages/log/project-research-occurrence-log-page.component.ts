import { ChangeDetectionStrategy, Component, computed, inject, input } from '@angular/core';
import { RouterLink } from '@angular/router';

import { IDENTITY_SERVICE } from '@core/auth/identity.service';
import { PageHeaderComponent } from '@shared/components/page-header/page-header.component';

import { projectDetailRouteForGroup } from '../../utils/project-detail-route.util';
import { ProjectOccurrenceLogPanelComponent } from './project-occurrence-log-panel.component';

@Component({
  selector: 'app-project-research-occurrence-log-page',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, PageHeaderComponent, ProjectOccurrenceLogPanelComponent],
  templateUrl: './project-research-occurrence-log-page.component.html',
  styleUrl: './project-log-page.scss',
})
export class ProjectResearchOccurrenceLogPageComponent {
  private readonly identity = inject(IDENTITY_SERVICE);

  readonly id = input.required<string>();

  protected readonly projectDetailRoute = computed(() =>
    projectDetailRouteForGroup(this.id(), this.identity.session()?.group),
  );
}
