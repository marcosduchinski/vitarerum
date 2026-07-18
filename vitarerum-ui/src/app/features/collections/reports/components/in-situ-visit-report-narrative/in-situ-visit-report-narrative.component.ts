import { ChangeDetectionStrategy, Component, input, output } from '@angular/core';
import { RouterLink } from '@angular/router';

import { InSituVisitReportNarrative } from '../../models/report.model';

function formatDateTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString('en-GB', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

@Component({
  selector: 'app-in-situ-visit-report-narrative',
  standalone: true,
  imports: [RouterLink],
  templateUrl: './in-situ-visit-report-narrative.component.html',
  styleUrl: './in-situ-visit-report-narrative.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class InSituVisitReportNarrativeComponent {
  readonly narrative = input<InSituVisitReportNarrative | null>(null);
  readonly auditTrailLink = input<readonly unknown[] | string | null>(null);

  readonly editNarrative = output<InSituVisitReportNarrative>();

  protected readonly formatDateTime = formatDateTime;

  protected requestNarrativeEdit(): void {
    const narrative = this.narrative();
    if (narrative) this.editNarrative.emit(narrative);
  }
}
