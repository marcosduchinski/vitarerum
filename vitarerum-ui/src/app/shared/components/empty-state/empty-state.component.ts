import { ChangeDetectionStrategy, Component, input } from '@angular/core';

import { LogoMarkComponent } from '@shared/components/logo-mark/logo-mark.component';

@Component({
  selector: 'app-empty-state',
  standalone: true,
  imports: [LogoMarkComponent],
  templateUrl: './empty-state.component.html',
  styleUrl: './empty-state.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class EmptyStateComponent {
  readonly title = input.required<string>();
  readonly message = input<string>();
}
