import { ChangeDetectionStrategy, Component, input, output } from '@angular/core';

export type ConfirmModalTone = 'default' | 'warning' | 'danger';

@Component({
  selector: 'app-confirm-modal',
  standalone: true,
  templateUrl: './confirm-modal.component.html',
  styleUrl: './confirm-modal.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ConfirmModalComponent {
  readonly open = input(false);
  readonly title = input.required<string>();
  readonly message = input('');
  readonly confirmLabel = input('Confirm');
  readonly cancelLabel = input('Cancel');
  readonly tone = input<ConfirmModalTone>('default');
  readonly pending = input(false);
  readonly confirmDisabled = input(false);

  readonly confirmed = output<void>();
  readonly cancelled = output<void>();

  protected confirm(): void {
    if (!this.pending() && !this.confirmDisabled()) {
      this.confirmed.emit();
    }
  }

  protected cancel(): void {
    if (!this.pending()) {
      this.cancelled.emit();
    }
  }
}
