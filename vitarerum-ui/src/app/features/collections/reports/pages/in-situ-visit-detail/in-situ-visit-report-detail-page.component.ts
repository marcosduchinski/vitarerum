import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  input,
  resource,
  signal,
} from '@angular/core';
import { DOCUMENT } from '@angular/common';
import { RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { ApiError, toApiError } from '@core/http/api-error.model';
import { ErrorMessageComponent } from '@shared/components/error-message/error-message.component';
import { LoadingStateComponent } from '@shared/components/loading-state/loading-state.component';

import { InSituVisitReportNarrativeComponent } from '../../components/in-situ-visit-report-narrative/in-situ-visit-report-narrative.component';
import { InSituVisitReportRailComponent } from '../../components/in-situ-visit-report-rail/in-situ-visit-report-rail.component';
import { InSituVisitReportRecordComponent } from '../../components/in-situ-visit-report-record/in-situ-visit-report-record.component';
import { InSituVisitCidocDialogComponent } from '../../components/in-situ-visit-cidoc-dialog/in-situ-visit-cidoc-dialog.component';
import { EditInSituVisitNarrativeDialogComponent } from '../../components/edit-in-situ-visit-narrative-dialog/edit-in-situ-visit-narrative-dialog.component';
import { InSituVisitReportNarrative } from '../../models/report.model';
import { REPORTS_API_SERVICE } from '../../services/reports-api.service';

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

@Component({
  selector: 'app-in-situ-visit-report-detail-page',
  standalone: true,
  imports: [
    RouterLink,
    LoadingStateComponent,
    ErrorMessageComponent,
    InSituVisitReportNarrativeComponent,
    InSituVisitReportRailComponent,
    InSituVisitReportRecordComponent,
    InSituVisitCidocDialogComponent,
    EditInSituVisitNarrativeDialogComponent,
  ],
  templateUrl: './in-situ-visit-report-detail-page.component.html',
  styleUrl: './in-situ-visit-report-detail-page.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class InSituVisitReportDetailPageComponent {
  private readonly reportsService = inject(REPORTS_API_SERVICE);
  private readonly document = inject(DOCUMENT);

  readonly projectId = input.required<string>();
  readonly reportId = input.required<string>();

  protected readonly detailResource = resource({
    params: () => ({ projectId: this.projectId(), reportId: this.reportId() }),
    loader: ({ params }) =>
      firstValueFrom(
        this.reportsService.getInSituVisitReportDetail(params.projectId, params.reportId),
      ),
  });

  protected readonly detail = computed(() =>
    this.detailResource.hasValue() ? this.detailResource.value() : null,
  );
  protected readonly detailError = computed<ApiError | null>(() => {
    const err = this.detailResource.error();
    return err ? toApiError(err) : null;
  });

  // The visit's protagonist headlines the report; the catalog code is demoted to the eyebrow.
  protected readonly headline = computed(
    () => this.detail()?.record?.visitorName ?? 'In-situ visit report',
  );
  protected readonly code = computed(() => this.detail()?.record?.code ?? null);

  protected readonly cidocDialogOpen = signal(false);
  protected readonly cidocRecordId = signal<string | null>(null);
  protected readonly narrativeEditorOpen = signal(false);
  protected readonly narrativeBeingEdited = signal<InSituVisitReportNarrative | null>(null);

  protected readonly formatDateTime = formatDateTime;
  protected readonly formatDate = formatDate;

  protected print(): void {
    this.document.defaultView?.print();
  }

  protected exportReport(): void {
    const report = this.detail();
    if (!report) return;

    // TODO: replace with the server-side report export endpoint (PDF) once available.
    const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const anchor = this.document.createElement('a');
    anchor.href = url;
    anchor.download = `${report.record?.code ?? report.id}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  protected openCidocDialog(recordId: string): void {
    this.cidocRecordId.set(recordId);
    this.cidocDialogOpen.set(true);
  }

  protected closeCidocDialog(): void {
    this.cidocDialogOpen.set(false);
    this.cidocRecordId.set(null);
  }

  protected openNarrativeEditor(narrative: InSituVisitReportNarrative): void {
    this.narrativeBeingEdited.set(narrative);
    this.narrativeEditorOpen.set(true);
  }

  protected closeNarrativeEditor(): void {
    this.narrativeEditorOpen.set(false);
    this.narrativeBeingEdited.set(null);
  }

  protected applyUpdatedNarrative(narrative: InSituVisitReportNarrative): void {
    const detail = this.detail();
    if (detail) {
      this.detailResource.set({ ...detail, narrative, narrativeId: narrative.narrativeId });
    }
    this.closeNarrativeEditor();
  }
}
