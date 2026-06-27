import { ChangeDetectionStrategy, Component, computed, inject, input } from '@angular/core';
import { RouterLink } from '@angular/router';

import { IDENTITY_SERVICE } from '@core/auth/identity.service';
import { PageHeaderComponent } from '@shared/components/page-header/page-header.component';

import { projectDetailRouteForGroup } from '../../utils/project-detail-route.util';
import { ProjectObjectLogPanelComponent } from './project-object-log-panel.component';

@Component({
  selector: 'app-project-exhibition-log-page',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, PageHeaderComponent, ProjectObjectLogPanelComponent],
  templateUrl: './project-exhibition-log-page.component.html',
  styleUrl: './project-log-page.scss',
})
export class ProjectExhibitionLogPageComponent {
  private readonly identity = inject(IDENTITY_SERVICE);

  readonly id = input.required<string>();

  protected readonly projectDetailRoute = computed(() =>
    projectDetailRouteForGroup(this.id(), this.identity.session()?.group),
  );
}
