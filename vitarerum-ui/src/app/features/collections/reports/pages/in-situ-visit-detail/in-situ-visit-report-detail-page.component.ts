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
import { InSituVisitReportRecordComponent } from '../../components/in-situ-visit-report-record/in-situ-visit-report-record.component';
import { EditInSituVisitNarrativeDialogComponent } from '../../components/edit-in-situ-visit-narrative-dialog/edit-in-situ-visit-narrative-dialog.component';
import {
  InSituVisitRecord,
  InSituVisitReportDetail,
  InSituVisitReportEvidenceItem,
  InSituVisitReportNarrative,
} from '../../models/report.model';
import { REPORTS_API_SERVICE } from '../../services/reports-api.service';

interface SimpleReportExportEvidenceItem {
  readonly sourceId: string;
  readonly description: string;
  readonly position: number;
  readonly attachments: readonly {
    readonly sourceId: string;
    readonly description: string;
    readonly reference: string;
    readonly position: number;
  }[];
}

interface SimpleReportExportPayload {
  readonly id: string;
  readonly createdAt: string;
  readonly createdBy: string;
  readonly projectId: string;
  readonly narrativeId: string;
  readonly inSituVisitRecordId: string;
  readonly code: string | null;
  readonly visitorName: string | null;
  readonly placeName: string | null;
  readonly visitBeginDate: string | null;
  readonly visitEndDate: string | null;
  readonly narrative: {
    readonly text: string;
    readonly type: string;
    readonly language: string;
    readonly generatedAt: string;
    readonly creativityTemperature: number;
    readonly validation: 'Conforms' | 'Needs review' | 'Validation unavailable';
  } | null;
  readonly record: {
    readonly id: string;
    readonly code: string;
    readonly generatedAt: string;
    readonly sourceProjectId: string | null;
    readonly sourceProjectTitle: string | null;
    readonly sourceProjectPurpose: string | null;
    readonly plannedBeginDate: string | null;
    readonly plannedEndDate: string | null;
    readonly requestedObjects: readonly SimpleReportExportEvidenceItem[];
    readonly inSituOccurrences: readonly SimpleReportExportEvidenceItem[];
    readonly inSituLogs: readonly SimpleReportExportEvidenceItem[];
    readonly inSituPublications: readonly SimpleReportExportEvidenceItem[];
  } | null;
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
    InSituVisitReportRecordComponent,
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
  protected readonly narrativeContext = computed(() => {
    const narrative = this.detail()?.narrative;
    if (!narrative) return null;
    const type = narrative.meta.resolvedNarrativeType.replace('_', ' ');
    const generatedAt = formatDateTime(narrative.generatedAt);
    return `${type} · ${narrative.meta.targetLanguage} · Generated ${generatedAt}`;
  });
  protected readonly validationLabel = computed(() => {
    const conforms = this.detail()?.narrative?.meta.validationConforms;
    if (conforms === true) return 'Conforms';
    if (conforms === false) return 'Needs review';
    return 'Validation unavailable';
  });
  protected readonly validationState = computed(() => {
    const conforms = this.detail()?.narrative?.meta.validationConforms;
    if (conforms === true) return 'ok';
    if (conforms === false) return 'warning';
    return 'unknown';
  });

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
    const blob = new Blob([JSON.stringify(this.toSimpleExportPayload(report), null, 2)], {
      type: 'application/json',
    });
    const url = URL.createObjectURL(blob);
    const anchor = this.document.createElement('a');
    anchor.href = url;
    anchor.download = `${report.record?.code ?? report.id}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  private toSimpleExportPayload(report: InSituVisitReportDetail): SimpleReportExportPayload {
    const narrative = report.narrative;
    const record = report.record;
    return {
      id: report.id,
      createdAt: report.createdAt,
      createdBy: report.createdBy,
      projectId: report.projectId,
      narrativeId: report.narrativeId,
      inSituVisitRecordId: report.inSituVisitRecordId,
      code: record?.code ?? null,
      visitorName: record?.visitorName ?? null,
      placeName: record?.placeName ?? null,
      visitBeginDate: record?.visitBeginDate ?? null,
      visitEndDate: record?.visitEndDate ?? null,
      narrative: narrative
        ? {
            text: narrative.text,
            type: narrative.meta.resolvedNarrativeType,
            language: narrative.meta.targetLanguage,
            generatedAt: narrative.generatedAt,
            creativityTemperature: narrative.meta.creativityTemperature,
            validation: this.validationLabel(),
          }
        : null,
      record: record ? this.toSimpleRecordExport(record) : null,
    };
  }

  private toSimpleRecordExport(record: InSituVisitRecord): SimpleReportExportPayload['record'] {
    return {
      id: record.id,
      code: record.code,
      generatedAt: record.generatedAt,
      sourceProjectId: record.sourceProjectId ?? null,
      sourceProjectTitle: record.sourceProjectTitle ?? null,
      sourceProjectPurpose: record.sourceProjectPurpose ?? null,
      plannedBeginDate: record.plannedBeginDate ?? null,
      plannedEndDate: record.plannedEndDate ?? null,
      requestedObjects: record.requestedObjects.map((item) => this.toSimpleEvidenceItem(item)),
      inSituOccurrences: record.inSituOccurrences.map((item) => this.toSimpleEvidenceItem(item)),
      inSituLogs: record.inSituLogs.map((item) => this.toSimpleEvidenceItem(item)),
      inSituPublications: record.inSituPublications.map((item) => this.toSimpleEvidenceItem(item)),
    };
  }

  private toSimpleEvidenceItem(
    item: InSituVisitReportEvidenceItem,
  ): SimpleReportExportEvidenceItem {
    return {
      sourceId: item.sourceId,
      description: item.description,
      position: item.position,
      attachments: item.attachments.map((attachment) => ({
        sourceId: attachment.sourceId,
        description: attachment.description,
        reference: attachment.reference,
        position: attachment.position,
      })),
    };
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
