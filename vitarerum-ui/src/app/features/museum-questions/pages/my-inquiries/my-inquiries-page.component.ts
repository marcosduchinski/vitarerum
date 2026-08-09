import { ChangeDetectionStrategy, Component } from '@angular/core';

import { EmptyStateComponent } from '@shared/components/empty-state/empty-state.component';
import { PageHeaderComponent } from '@shared/components/page-header/page-header.component';

@Component({
  selector: 'app-my-inquiries-page',
  standalone: true,
  imports: [PageHeaderComponent, EmptyStateComponent],
  templateUrl: './my-inquiries-page.component.html',
  styleUrl: './my-inquiries-page.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class MyInquiriesPageComponent {}
