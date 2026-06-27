import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

import { InSituVisitRecord, InSituVisitReportNarrative } from '../../models/report.model';

interface EvidenceTotal {
  readonly key: string;
  readonly label: string;
  readonly count: number;
}

function formatDate(date: string): string {
  try {
    return new Date(`${date}T00:00:00`).toLocaleDateString('en-GB', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
    });
  } catch {
    return date;
  }
}

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
  selector: 'app-in-situ-visit-report-rail',
  standalone: true,
  templateUrl: './in-situ-visit-report-rail.component.html',
  styleUrl: './in-situ-visit-report-rail.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class InSituVisitReportRailComponent {
  readonly record = input<InSituVisitRecord | null>(null);
  readonly narrative = input<InSituVisitReportNarrative | null>(null);

  protected readonly totals = computed<readonly EvidenceTotal[]>(() => {
    const record = this.record();
    if (!record) return [];

    return [
      { key: 'objects', label: 'Requested objects', count: record.requestedObjects.length },
      { key: 'occurrences', label: 'Occurrences', count: record.inSituOccurrences.length },
      { key: 'logs', label: 'Visit logs', count: record.inSituLogs.length },
      { key: 'publications', label: 'Publications', count: record.inSituPublications.length },
    ];
  });

  protected readonly evidenceTotal = computed(() =>
    this.totals().reduce((sum, total) => sum + total.count, 0),
  );

  protected readonly formatDate = formatDate;
  protected readonly formatDateTime = formatDateTime;
}
