import { HttpClient, HttpParams } from '@angular/common/http';
import { inject, Injectable, InjectionToken } from '@angular/core';
import { API_BASE_URL } from '@core/config/app-config.model';
import { buildApiUrl } from '@core/http/api-url.util';
import { map } from 'rxjs';

import {
  CidocCrmJsonObject,
  CreateInSituVisitReportRequest,
  InSituVisitRecord,
  InSituVisitReport,
  InSituVisitReportAttachment,
  InSituVisitReportDetail,
  InSituVisitReportEvidenceItem,
  InSituVisitReportListPage,
  InSituVisitReportNarrative,
  InSituVisitReportsQuery,
  UpdateInSituVisitNarrativeRequest,
} from '../models/report.model';

interface NarrativeDto {
  readonly narrative_id: string;
  readonly record_id: string;
  readonly generated_at: string;
  readonly meta: {
    readonly resolved_narrative_type: string;
    readonly resolution_source: string;
    readonly target_language: string;
    readonly creativity_temperature: number;
    readonly llm_model: string;
  };
  readonly data: { readonly narrative?: string };
}

interface AttachmentDto {
  readonly id: string;
  readonly sourceId: string;
  readonly description: string;
  readonly reference: string;
  readonly position: number;
}

interface EvidenceItemDto {
  readonly id: string;
  readonly sourceId: string;
  readonly description: string;
  readonly position: number;
  readonly attachments?: readonly AttachmentDto[];
}

interface InSituVisitRecordDto {
  readonly id: string;
  readonly code: string;
  readonly visitBeginDate: string;
  readonly visitEndDate: string;
  readonly visitorName: string;
  readonly placeName: string;
  readonly generatedAt: string;
  readonly requestedObjects: readonly EvidenceItemDto[];
  readonly inSituOccurrences: readonly EvidenceItemDto[];
  readonly inSituLogs: readonly EvidenceItemDto[];
  readonly inSituPublications: readonly EvidenceItemDto[];
}

interface InSituVisitReportDetailDto extends InSituVisitReport {
  readonly narrative: NarrativeDto | null;
  readonly record: InSituVisitRecordDto | null;
}

export const REPORTS_API_SERVICE = new InjectionToken<ReportsApiService>('REPORTS_API_SERVICE');

@Injectable()
export class ReportsApiService {
  private readonly http = inject(HttpClient);
  private readonly apiBaseUrl = inject(API_BASE_URL);

  listInSituVisitReports(query: InSituVisitReportsQuery = {}) {
    return this.http.get<InSituVisitReportListPage>(
      this.url('/reports/collection-use/in_situ_visit'),
      { params: this.buildPaginationParams(query) },
    );
  }

  createInSituVisitReport(projectId: string, request: CreateInSituVisitReportRequest) {
    return this.http.post<InSituVisitReport>(
      this.url(`/reports/collection-use/${projectId}/in_situ_visit`),
      {
        target_language: request.targetLanguage,
        narrative_type: request.narrativeType,
        creativity_temperature: request.creativityTemperature,
      },
    );
  }

  getInSituVisitReportDetail(projectId: string, reportId: string) {
    return this.http
      .get<InSituVisitReportDetailDto>(
        this.url(`/reports/collection-use/${projectId}/in_situ_visit/${reportId}/detail`),
      )
      .pipe(map((detail) => this.toDetail(detail)));
  }

  getInSituVisitCidocCrm(recordId: string) {
    return this.http.get<CidocCrmJsonObject>(
      this.url(`/cedoc-mapping/in-situ-visit/${recordId}/cidoc-crm`),
    );
  }

  updateInSituVisitNarrative(
    recordId: string,
    narrativeId: string,
    request: UpdateInSituVisitNarrativeRequest,
  ) {
    return this.http
      .patch<NarrativeDto>(
        this.url(`/cedoc-mapping/in-situ-visit/${recordId}/narratives/${narrativeId}`),
        { narrative: request.narrative },
      )
      .pipe(map((narrative) => this.toNarrative(narrative)));
  }

  private buildPaginationParams(query: InSituVisitReportsQuery): HttpParams {
    let params = new HttpParams();
    if (query.page !== undefined) params = params.set('page', String(query.page));
    if (query.size !== undefined) params = params.set('size', String(query.size));
    return params;
  }

  private toDetail(detail: InSituVisitReportDetailDto): InSituVisitReportDetail {
    return {
      id: detail.id,
      createdAt: detail.createdAt,
      createdBy: detail.createdBy,
      projectId: detail.projectId,
      narrativeId: detail.narrativeId,
      inSituVisitRecordId: detail.inSituVisitRecordId,
      narrative: detail.narrative ? this.toNarrative(detail.narrative) : null,
      record: detail.record ? this.toRecord(detail.record) : null,
    };
  }

  private toNarrative(narrative: NarrativeDto): InSituVisitReportNarrative {
    return {
      narrativeId: narrative.narrative_id,
      recordId: narrative.record_id,
      generatedAt: narrative.generated_at,
      meta: {
        resolvedNarrativeType: narrative.meta.resolved_narrative_type,
        resolutionSource: narrative.meta.resolution_source,
        targetLanguage: narrative.meta.target_language,
        creativityTemperature: narrative.meta.creativity_temperature,
        llmModel: narrative.meta.llm_model,
      },
      text: narrative.data.narrative ?? '',
    };
  }

  private toRecord(record: InSituVisitRecordDto): InSituVisitRecord {
    return {
      id: record.id,
      code: record.code,
      visitBeginDate: record.visitBeginDate,
      visitEndDate: record.visitEndDate,
      visitorName: record.visitorName,
      placeName: record.placeName,
      generatedAt: record.generatedAt,
      requestedObjects: record.requestedObjects.map((item) => this.toEvidenceItem(item)),
      inSituOccurrences: record.inSituOccurrences.map((item) => this.toEvidenceItem(item)),
      inSituLogs: record.inSituLogs.map((item) => this.toEvidenceItem(item)),
      inSituPublications: record.inSituPublications.map((item) => this.toEvidenceItem(item)),
    };
  }

  private toEvidenceItem(item: EvidenceItemDto): InSituVisitReportEvidenceItem {
    return {
      id: item.id,
      sourceId: item.sourceId,
      description: item.description,
      position: item.position,
      attachments: (item.attachments ?? []).map((attachment) => this.toAttachment(attachment)),
    };
  }

  private toAttachment(attachment: AttachmentDto): InSituVisitReportAttachment {
    return { ...attachment };
  }

  private url(path: string): string {
    return buildApiUrl(this.apiBaseUrl, path);
  }
}
