import { ChangeDetectionStrategy, Component, computed, inject, input } from '@angular/core';
import { RouterLink } from '@angular/router';

import { IDENTITY_SERVICE } from '@core/auth/identity.service';
import { PageHeaderComponent } from '@shared/components/page-header/page-header.component';

import { projectDetailRouteForGroup } from '../../utils/project-detail-route.util';
import { ProjectPublicationLogPanelComponent } from './project-publication-log-panel.component';

@Component({
  selector: 'app-project-publication-log-page',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, PageHeaderComponent, ProjectPublicationLogPanelComponent],
  templateUrl: './project-publication-log-page.component.html',
  styleUrl: './project-log-page.scss',
})
export class ProjectPublicationLogPageComponent {
  private readonly identity = inject(IDENTITY_SERVICE);

  readonly id = input.required<string>();

  protected readonly projectDetailRoute = computed(() =>
    projectDetailRouteForGroup(this.id(), this.identity.session()?.group),
  );
}
