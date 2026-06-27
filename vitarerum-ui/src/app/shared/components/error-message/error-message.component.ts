import { ChangeDetectionStrategy, Component, computed, input, output } from '@angular/core';
import { ApiError, getApiErrorPresentation } from '@core/http/api-error.model';

export type ErrorMessageTone = 'danger' | 'info' | 'warning';

@Component({
  selector: 'app-error-message',
  standalone: true,
  templateUrl: './error-message.component.html',
  styleUrl: './error-message.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ErrorMessageComponent {
  readonly title = input<string>('');
  readonly message = input<string>('');
  readonly tone = input<ErrorMessageTone>('danger');
  readonly apiError = input<ApiError | null>(null);
  readonly retry = output<void>();

  private readonly presentation = computed(() => {
    const err = this.apiError();
    return err ? getApiErrorPresentation(err) : null;
  });

  protected readonly resolvedTitle = computed(() => this.presentation()?.title ?? this.title());
  protected readonly resolvedMessage = computed(() => this.presentation()?.message ?? this.message());
  protected readonly resolvedTone = computed(() => this.presentation()?.tone ?? this.tone());
  protected readonly showRetry = computed(() => this.presentation()?.retryable ?? false);
  protected readonly fieldErrors = computed(() => this.apiError()?.fieldErrors ?? []);
}
