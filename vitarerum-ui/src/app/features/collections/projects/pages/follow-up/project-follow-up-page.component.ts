import { ChangeDetectionStrategy, Component, input } from '@angular/core';

@Component({
  selector: 'app-project-follow-up-page',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<section class="project-follow-up" aria-label="Create follow-up project"></section>`,
})
export class ProjectFollowUpPageComponent {
  readonly id = input.required<string>();
}
