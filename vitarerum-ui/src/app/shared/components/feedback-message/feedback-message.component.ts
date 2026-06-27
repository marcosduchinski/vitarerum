import { ChangeDetectionStrategy, Component, computed, input, output } from '@angular/core';

export type FeedbackMessageTone = 'success' | 'info' | 'warning' | 'danger';

@Component({
  selector: 'app-feedback-message',
  standalone: true,
  templateUrl: './feedback-message.component.html',
  styleUrl: './feedback-message.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class FeedbackMessageComponent {
  readonly title = input.required<string>();
  readonly message = input.required<string>();
  readonly tone = input<FeedbackMessageTone>('info');
  readonly dismissible = input(false);
  readonly dismissed = output<void>();

  protected readonly role = computed(() =>
    this.tone() === 'warning' || this.tone() === 'danger' ? 'alert' : 'status',
  );
  protected readonly ariaLive = computed(() =>
    this.tone() === 'warning' || this.tone() === 'danger' ? 'assertive' : 'polite',
  );
}
