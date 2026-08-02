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
  InSituVisitReportAuditTrail,
  InSituVisitReportAttachment,
  InSituVisitReportDetail,
  InSituVisitReportEvidenceItem,
  InSituVisitReportListPage,
  InSituVisitReportNarrative,
  InSituVisitNarrativeRevision,
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
    readonly facts_snapshot_id?: string | null;
    readonly prompt_version_id?: string | null;
    readonly prompt_version?: string | null;
    readonly model_response_hash?: string | null;
    readonly validation_conforms?: boolean | null;
    readonly validation_findings?: readonly {
      readonly code: string;
      readonly message: string;
      readonly evidence: string;
    }[];
  };
  readonly data: { readonly narrative?: string };
  readonly facts_snapshot?: {
    readonly id: string;
    readonly record_id: string;
    readonly payload_json: string;
    readonly payload_hash: string;
    readonly builder_version: string;
    readonly prompt_version: string;
    readonly cidoc_document_json?: string | null;
    readonly cidoc_validation_report?: string | null;
    readonly cidoc_conforms?: boolean | null;
    readonly created_at: string;
  } | null;
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
  readonly recordSchemaVersion?: number | null;
  readonly sourceProjectId?: string | null;
  readonly sourceProjectTitle?: string | null;
  readonly sourceProjectPurpose?: string | null;
  readonly plannedBeginDate?: string | null;
  readonly plannedEndDate?: string | null;
  readonly executionEvidenceType?: string | null;
  readonly executionOccurredAt?: string | null;
  readonly executionRecordedBy?: string | null;
  readonly executionEvidenceGaps?: readonly string[];
  readonly mappingVersion?: string | null;
  readonly crmVersion?: string | null;
  readonly requestedObjects: readonly EvidenceItemDto[];
  readonly inSituOccurrences: readonly EvidenceItemDto[];
  readonly inSituLogs: readonly EvidenceItemDto[];
  readonly inSituPublications: readonly EvidenceItemDto[];
}

interface InSituVisitReportDetailDto extends InSituVisitReport {
  readonly narrative: NarrativeDto | null;
  readonly record: InSituVisitRecordDto | null;
}

interface NarrativeRevisionDto {
  readonly id: string;
  readonly narrative_id: string;
  readonly record_id: string;
  readonly previous_narrative: string;
  readonly revised_narrative: string;
  readonly edited_by?: string | null;
  readonly edited_at: string;
}

interface NarrativeRevisionPageDto {
  readonly content: readonly NarrativeRevisionDto[];
  readonly page: number;
  readonly size: number;
  readonly total_elements: number;
  readonly total_pages: number;
}

interface InSituVisitAuditTrailDto extends InSituVisitReportDetailDto {
  readonly evidence: {
    readonly recordId: string | null;
    readonly projectId: string;
    readonly code: string | null;
    readonly executionEvidenceType: string | null;
    readonly executionOccurredAt: string | null;
    readonly executionRecordedBy: string | null;
    readonly executionEvidenceGaps: readonly string[];
    readonly approvedAt: string | null;
    readonly approvedBy: string | null;
    readonly approvalNote: string | null;
  };
  readonly cidoc: {
    readonly documentJson: string | null;
    readonly mappingVersion: string | null;
    readonly crmVersion: string | null;
    readonly recordSchemaVersion: number | null;
    readonly conforms: boolean | null;
    readonly validationReport: string | null;
  };
  readonly facts: {
    readonly snapshotId: string | null;
    readonly payloadJson: string | null;
    readonly payloadHash: string | null;
    readonly builderVersion: string | null;
    readonly promptVersion: string | null;
    readonly createdAt: string | null;
  };
  readonly generation: {
    readonly narrativeId: string | null;
    readonly generatedAt: string | null;
    readonly narrativeType: string | null;
    readonly resolutionSource: string | null;
    readonly targetLanguage: string | null;
    readonly creativityTemperature: number | null;
    readonly llmModel: string | null;
    readonly promptVersionId: string | null;
    readonly promptVersion: string | null;
    readonly responseHash: string | null;
  };
  readonly validation: {
    readonly conforms: boolean | null;
    readonly findings: readonly {
      readonly code: string;
      readonly message: string;
      readonly evidence: string;
    }[];
  };
  readonly revisions: NarrativeRevisionPageDto | null;
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

  getInSituVisitReportAuditTrail(projectId: string, reportId: string) {
    return this.http
      .get<InSituVisitAuditTrailDto>(
        this.url(`/reports/collection-use/${projectId}/in_situ_visit/${reportId}/audit-trail`),
      )
      .pipe(map((audit) => this.toAuditTrail(audit)));
  }

  getInSituVisitCidocCrm(recordId: string) {
    return this.http.get<CidocCrmJsonObject>(
      this.url(`/cidoc-mapping/in-situ-visit/${recordId}/cidoc-crm`),
    );
  }

  updateInSituVisitNarrative(
    recordId: string,
    narrativeId: string,
    request: UpdateInSituVisitNarrativeRequest,
  ) {
    return this.http
      .patch<NarrativeDto>(
        this.url(`/cidoc-mapping/in-situ-visit/${recordId}/narratives/${narrativeId}`),
        { narrative: request.narrative },
      )
      .pipe(map((narrative) => this.toNarrative(narrative)));
  }

  private buildPaginationParams(query: InSituVisitReportsQuery): HttpParams {
    let params = new HttpParams();
    if (query.page !== undefined) params = params.set('page', String(query.page));
    if (query.size !== undefined) params = params.set('size', String(query.size));
    if (query.search) params = params.set('search', query.search);
    if (query.generatedFrom) params = params.set('generatedFrom', query.generatedFrom);
    if (query.generatedTo) params = params.set('generatedTo', query.generatedTo);
    if (query.visitFrom) params = params.set('visitFrom', query.visitFrom);
    if (query.visitTo) params = params.set('visitTo', query.visitTo);
    if (query.narrativeType) params = params.set('narrativeType', query.narrativeType);
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
        factsSnapshotId: narrative.meta.facts_snapshot_id ?? null,
        promptVersionId: narrative.meta.prompt_version_id ?? null,
        promptVersion: narrative.meta.prompt_version ?? null,
        modelResponseHash: narrative.meta.model_response_hash ?? null,
        validationConforms: narrative.meta.validation_conforms ?? null,
        validationFindings: narrative.meta.validation_findings ?? [],
      },
      text: narrative.data.narrative ?? '',
      factsSnapshot: narrative.facts_snapshot
        ? {
            id: narrative.facts_snapshot.id,
            recordId: narrative.facts_snapshot.record_id,
            payloadJson: narrative.facts_snapshot.payload_json,
            payloadHash: narrative.facts_snapshot.payload_hash,
            builderVersion: narrative.facts_snapshot.builder_version,
            promptVersion: narrative.facts_snapshot.prompt_version,
            cidocDocumentJson: narrative.facts_snapshot.cidoc_document_json ?? null,
            cidocValidationReport: narrative.facts_snapshot.cidoc_validation_report ?? null,
            cidocConforms: narrative.facts_snapshot.cidoc_conforms ?? null,
            createdAt: narrative.facts_snapshot.created_at,
          }
        : null,
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
      recordSchemaVersion: record.recordSchemaVersion ?? null,
      sourceProjectId: record.sourceProjectId ?? null,
      sourceProjectTitle: record.sourceProjectTitle ?? null,
      sourceProjectPurpose: record.sourceProjectPurpose ?? null,
      plannedBeginDate: record.plannedBeginDate ?? null,
      plannedEndDate: record.plannedEndDate ?? null,
      executionEvidenceType: record.executionEvidenceType ?? null,
      executionOccurredAt: record.executionOccurredAt ?? null,
      executionRecordedBy: record.executionRecordedBy ?? null,
      executionEvidenceGaps: record.executionEvidenceGaps ?? [],
      mappingVersion: record.mappingVersion ?? null,
      crmVersion: record.crmVersion ?? null,
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

  private toAuditTrail(audit: InSituVisitAuditTrailDto): InSituVisitReportAuditTrail {
    return {
      id: audit.id,
      createdAt: audit.createdAt,
      createdBy: audit.createdBy,
      projectId: audit.projectId,
      narrativeId: audit.narrativeId,
      inSituVisitRecordId: audit.inSituVisitRecordId,
      record: audit.record ? this.toRecord(audit.record) : null,
      narrative: audit.narrative ? this.toNarrative(audit.narrative) : null,
      evidence: { ...audit.evidence },
      cidoc: { ...audit.cidoc },
      facts: { ...audit.facts },
      generation: { ...audit.generation },
      validation: { ...audit.validation },
      revisions: audit.revisions
        ? {
            content: audit.revisions.content.map((revision) => this.toRevision(revision)),
            page: audit.revisions.page,
            size: audit.revisions.size,
            totalElements: audit.revisions.total_elements,
            totalPages: audit.revisions.total_pages,
          }
        : null,
    };
  }

  private toRevision(revision: NarrativeRevisionDto): InSituVisitNarrativeRevision {
    return {
      id: revision.id,
      narrativeId: revision.narrative_id,
      recordId: revision.record_id,
      previousNarrative: revision.previous_narrative,
      revisedNarrative: revision.revised_narrative,
      editedBy: revision.edited_by ?? null,
      editedAt: revision.edited_at,
    };
  }

  private url(path: string): string {
    return buildApiUrl(this.apiBaseUrl, path);
  }
}
