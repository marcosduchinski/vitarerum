import { ChangeDetectionStrategy, Component, input } from '@angular/core';

import { ProjectStaffDetailPageComponent } from '../staff-detail/project-staff-detail-page.component';

@Component({
  selector: 'app-project-curatorial-detail-page',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ProjectStaffDetailPageComponent],
  template: `
    <app-project-staff-detail-page
      sectionLabel="Curatorial"
      [id]="id()"
      [returnTo]="returnTo()"
      [returnLabel]="returnLabel()"
    />
  `,
})
export class ProjectCuratorialDetailPageComponent {
  readonly id = input.required<string>();
  readonly returnTo = input<string>();
  readonly returnLabel = input<string>();
}
