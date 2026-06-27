import { ChangeDetectionStrategy, Component, input, output, signal } from '@angular/core';
import { FormField, form, max, min } from '@angular/forms/signals';

import { ApiError } from '@core/http/api-error.model';
import { ConfirmModalComponent } from '@shared/components/confirm-modal/confirm-modal.component';
import { ErrorMessageComponent } from '@shared/components/error-message/error-message.component';

import { CreateInSituVisitReportRequest } from '../../models/report.model';

const DEFAULT_REPORT_REQUEST: CreateInSituVisitReportRequest = {
  targetLanguage: 'pt',
  narrativeType: 'institutional',
  creativityTemperature: 0.3,
};

@Component({
  selector: 'app-create-in-situ-visit-report-modal',
  standalone: true,
  imports: [FormField, ConfirmModalComponent, ErrorMessageComponent],
  templateUrl: './create-in-situ-visit-report-modal.component.html',
  styleUrl: './create-in-situ-visit-report-modal.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CreateInSituVisitReportModalComponent {
  readonly open = input(false);
  readonly pending = input(false);
  readonly apiError = input<ApiError | null>(null);

  readonly submitted = output<CreateInSituVisitReportRequest>();
  readonly cancelled = output<void>();

  protected readonly formModel = signal<CreateInSituVisitReportRequest>({
    ...DEFAULT_REPORT_REQUEST,
  });

  // Signal Forms is experimental in Angular 21. Keeping it local to this modal
  // limits the migration surface if its API changes.
  protected readonly reportForm = form(this.formModel, (path) => {
    min(path.creativityTemperature, 0, { message: 'Creativity must be at least 0.0.' });
    max(path.creativityTemperature, 1, { message: 'Creativity must be at most 1.0.' });
  });

  protected submit(): void {
    this.reportForm().markAsTouched();
    if (this.pending() || this.reportForm().invalid()) return;

    this.submitted.emit({ ...this.formModel() });
  }

  protected cancel(): void {
    if (this.pending()) return;
    this.cancelled.emit();
  }
}
