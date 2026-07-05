import { ChangeDetectionStrategy, Component } from '@angular/core';
import { RouterLink } from '@angular/router';

import { PageHeaderComponent } from '@shared/components/page-header/page-header.component';

/**
 * Public entry point offering two distinct paths, so simple questions no
 * longer get funnelled into the formal proposal flow (see
 * docs/plans/museum-questions-public-page-plan.md).
 */
@Component({
  selector: 'app-public-landing-page',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [PageHeaderComponent, RouterLink],
  templateUrl: './public-landing-page.component.html',
  styleUrl: './public-landing-page.component.scss',
})
export class PublicLandingPageComponent {}
