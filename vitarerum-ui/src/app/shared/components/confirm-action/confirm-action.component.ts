import { ChangeDetectionStrategy, Component, input, output } from '@angular/core';

@Component({
  selector: 'app-confirm-action',
  standalone: true,
  templateUrl: './confirm-action.component.html',
  styleUrl: './confirm-action.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ConfirmActionComponent {
  readonly title = input.required<string>();
  readonly message = input.required<string>();
  readonly confirmLabel = input('Confirm');
  readonly cancelLabel = input('Cancel');
  readonly disabled = input(false);

  readonly confirmed = output<void>();
  readonly cancelled = output<void>();

  protected confirm(): void {
    if (!this.disabled()) {
      this.confirmed.emit();
    }
  }

  protected cancel(): void {
    this.cancelled.emit();
  }
}
