import { inject, Injectable } from '@angular/core';
import { IDENTITY_SERVICE } from '@core/auth/identity.service';
import { makePageFrom, MockProjectState } from '@features/collections/proposals/mocks/mock-data';
import { Observable, of, throwError } from 'rxjs';

import {
  CidocCrmJsonObject,
  CreateInSituVisitReportRequest,
  InSituVisitRecord,
  InSituVisitReport,
  InSituVisitReportAuditTrail,
  InSituVisitReportDetail,
  InSituVisitReportEvidenceItem,
  InSituVisitReportListItem,
  InSituVisitReportListPage,
  InSituVisitReportNarrative,
  InSituVisitNarrativeRevision,
  InSituVisitReportsQuery,
  InSituVisitReportNarrativeType,
  InSituVisitReportTargetLanguage,
  UpdateInSituVisitNarrativeRequest,
} from '../models/report.model';

const TARGET_LANGUAGES: readonly InSituVisitReportTargetLanguage[] = ['pt', 'en'];
const NARRATIVE_TYPES: readonly InSituVisitReportNarrativeType[] = [
  'institutional',
  'scientific',
  'social_media',
];

@Injectable()
export class ReportsApiServiceMock {
  private readonly identity = inject(IDENTITY_SERVICE);
  private readonly state = inject(MockProjectState);
  private readonly generatedReports: InSituVisitReport[] = [];
  private readonly generatedDetails = new Map<string, InSituVisitReportDetail>();
  private readonly revisions = new Map<string, InSituVisitNarrativeRevision[]>();
  private reportSequence = 0;

  listInSituVisitReports(
    query: InSituVisitReportsQuery = {},
  ): Observable<InSituVisitReportListPage> {
    if (!this.identity.isStaff()) {
      return throwError(() => ({
        status: 403,
        error: 'ACCESS_DENIED',
        message: 'Reports are restricted to use-of-collections staff',
      }));
    }

    const reports = [...this.generatedReports]
      .sort((a, b) => b.createdAt.localeCompare(a.createdAt))
      .map((report) => this.toListItem(report));
    return of(
      makePageFrom(
        reports.map((report) => structuredClone(report)),
        query,
      ),
    );
  }

  createInSituVisitReport(
    projectId: string,
    request: CreateInSituVisitReportRequest,
  ): Observable<InSituVisitReport> {
    if (!this.identity.isStaff()) {
      return this.fail(403, 'ACCESS_DENIED', 'Reports are restricted to staff');
    }

    const createdBy = this.identity.getPermissionId();
    if (!createdBy) {
      return this.fail(401, 'UNAUTHENTICATED', 'An active permission is required');
    }

    const project = this.state.projects.get(projectId);
    if (!project) {
      return this.fail(404, 'PROJECT_NOT_FOUND', `No project found with id ${projectId}`);
    }
    if (project.type !== 'IN_SITU_VISIT') {
      return this.fail(409, 'INVALID_USE_TYPE', 'The project is not an in-situ visit');
    }
    if (!TARGET_LANGUAGES.includes(request.targetLanguage)) {
      return this.fail(400, 'INVALID_TARGET_LANGUAGE', 'Unsupported target language');
    }
    if (!NARRATIVE_TYPES.includes(request.narrativeType)) {
      return this.fail(400, 'INVALID_NARRATIVE_TYPE', 'Unsupported narrative type');
    }
    if (
      !Number.isFinite(request.creativityTemperature) ||
      request.creativityTemperature < 0 ||
      request.creativityTemperature > 1
    ) {
      return this.fail(
        400,
        'INVALID_CREATIVITY_TEMPERATURE',
        'Creativity temperature must be between 0.0 and 1.0',
      );
    }

    const sequence = ++this.reportSequence;
    const suffix = String(sequence).padStart(4, '0');
    const report: InSituVisitReport = {
      id: `mock-in-situ-visit-report-${suffix}`,
      createdAt: new Date(Date.UTC(2026, 5, 22, 10, 30, sequence - 1)).toISOString(),
      createdBy,
      projectId,
      narrativeId: `mock-narrative-${suffix}`,
      inSituVisitRecordId: `mock-in-situ-visit-record-${suffix}`,
    };
    this.generatedReports.push(report);
    this.generatedDetails.set(report.id, this.buildDetail(report, project, request, suffix));
    return of(structuredClone(report));
  }

  getInSituVisitReportDetail(
    projectId: string,
    reportId: string,
  ): Observable<InSituVisitReportDetail> {
    if (!this.identity.isStaff()) {
      return this.fail(403, 'ACCESS_DENIED', 'Reports are restricted to staff');
    }

    const detail = this.generatedDetails.get(reportId);
    if (!detail || detail.projectId !== projectId) {
      return this.fail(
        404,
        'REPORT_NOT_FOUND',
        `No report found with id ${reportId} for project ${projectId}`,
      );
    }

    return of(structuredClone(detail));
  }

  getInSituVisitReportAuditTrail(
    projectId: string,
    reportId: string,
  ): Observable<InSituVisitReportAuditTrail> {
    if (!this.identity.isStaff()) {
      return this.fail(403, 'ACCESS_DENIED', 'Reports are restricted to staff');
    }

    const detail = this.generatedDetails.get(reportId);
    if (!detail || detail.projectId !== projectId) {
      return this.fail(
        404,
        'REPORT_NOT_FOUND',
        `No report found with id ${reportId} for project ${projectId}`,
      );
    }

    const record = detail.record;
    const narrative = detail.narrative;
    const content = this.revisions.get(reportId) ?? [];
    return of(
      structuredClone({
        ...detail,
        evidence: {
          recordId: record?.id ?? null,
          projectId,
          code: record?.code ?? null,
          executionEvidenceType: record?.executionEvidenceType ?? 'project_completed',
          executionOccurredAt: record?.executionOccurredAt ?? detail.createdAt,
          executionRecordedBy: record?.executionRecordedBy ?? detail.createdBy,
          executionEvidenceGaps: record?.executionEvidenceGaps ?? [],
          approvedAt: null,
          approvedBy: null,
          approvalNote: null,
        },
        cidoc: {
          documentJson: narrative?.factsSnapshot?.cidocDocumentJson ?? '{"@graph":[]}',
          mappingVersion: record?.mappingVersion ?? 'in-situ-visit-cidoc-v2',
          crmVersion: record?.crmVersion ?? '7.1.3',
          recordSchemaVersion: record?.recordSchemaVersion ?? 2,
          conforms: narrative?.factsSnapshot?.cidocConforms ?? true,
          validationReport:
            narrative?.factsSnapshot?.cidocValidationReport ?? 'Validation Report\nConforms: True',
        },
        facts: {
          snapshotId: narrative?.factsSnapshot?.id ?? null,
          payloadJson: narrative?.factsSnapshot?.payloadJson ?? null,
          payloadHash: narrative?.factsSnapshot?.payloadHash ?? null,
          builderVersion: narrative?.factsSnapshot?.builderVersion ?? null,
          promptVersion: narrative?.factsSnapshot?.promptVersion ?? null,
          createdAt: narrative?.factsSnapshot?.createdAt ?? null,
        },
        generation: {
          narrativeId: narrative?.narrativeId ?? null,
          generatedAt: narrative?.generatedAt ?? null,
          narrativeType: narrative?.meta.resolvedNarrativeType ?? null,
          resolutionSource: narrative?.meta.resolutionSource ?? null,
          targetLanguage: narrative?.meta.targetLanguage ?? null,
          creativityTemperature: narrative?.meta.creativityTemperature ?? null,
          llmModel: narrative?.meta.llmModel ?? null,
          promptVersionId: narrative?.meta.promptVersionId ?? null,
          promptVersion: narrative?.meta.promptVersion ?? null,
          responseHash: narrative?.meta.modelResponseHash ?? null,
        },
        validation: {
          conforms: narrative?.meta.validationConforms ?? true,
          findings: narrative?.meta.validationFindings ?? [],
        },
        revisions: {
          content,
          page: 0,
          size: 100,
          totalElements: content.length,
          totalPages: content.length ? 1 : 0,
        },
      }),
    );
  }

  getInSituVisitCidocCrm(recordId: string): Observable<CidocCrmJsonObject> {
    if (!this.identity.isStaff()) {
      return this.fail(403, 'ACCESS_DENIED', 'Staff access required');
    }

    const record = this.findDetailByRecordId(recordId)?.record;
    if (!record) return this.fail(404, 'IN_SITU_VISIT_NOT_FOUND', `Record ${recordId} not found`);

    return of({
      '@context': { crm: 'http://www.cidoc-crm.org/cidoc-crm/' },
      '@graph': [
        {
          '@id': `ex:visit/${record.id}`,
          '@type': 'crm:E7_Activity',
        },
      ],
    });
  }

  updateInSituVisitNarrative(
    recordId: string,
    narrativeId: string,
    request: UpdateInSituVisitNarrativeRequest,
  ): Observable<InSituVisitReportNarrative> {
    if (!this.identity.isStaff()) {
      return this.fail(403, 'ACCESS_DENIED', 'Staff access required');
    }

    const narrativeText = request.narrative.trim();
    if (!narrativeText) {
      return this.fail(422, 'VALIDATION_ERROR', 'Narrative is required');
    }

    const detail = this.findDetailByRecordId(recordId);
    if (!detail?.narrative || detail.narrative.narrativeId !== narrativeId) {
      return this.fail(404, 'NARRATIVE_NOT_FOUND', `Narrative ${narrativeId} not found`);
    }

    const narrative = { ...detail.narrative, text: narrativeText };
    this.generatedDetails.set(detail.id, { ...detail, narrative });
    this.revisions.set(detail.id, [
      {
        id: `mock-revision-${detail.id}-${Date.now()}`,
        narrativeId,
        recordId,
        previousNarrative: detail.narrative.text,
        revisedNarrative: narrativeText,
        editedBy: this.identity.getPermissionId(),
        editedAt: new Date().toISOString(),
      },
      ...(this.revisions.get(detail.id) ?? []),
    ]);
    return of(structuredClone(narrative));
  }

  private toListItem(report: InSituVisitReport): InSituVisitReportListItem {
    const detail = this.generatedDetails.get(report.id);
    const record = detail?.record ?? null;
    const meta = detail?.narrative?.meta ?? null;
    return {
      ...report,
      code: record?.code ?? null,
      visitorName: record?.visitorName ?? null,
      placeName: record?.placeName ?? null,
      visitBeginDate: record?.visitBeginDate ?? null,
      visitEndDate: record?.visitEndDate ?? null,
      narrativeType: meta?.resolvedNarrativeType ?? null,
      targetLanguage: meta?.targetLanguage ?? null,
      creativityTemperature: meta?.creativityTemperature ?? null,
    };
  }

  private findDetailByRecordId(recordId: string): InSituVisitReportDetail | null {
    for (const detail of this.generatedDetails.values()) {
      if (detail.inSituVisitRecordId === recordId) return detail;
    }
    return null;
  }

  private buildDetail(
    report: InSituVisitReport,
    project: {
      readonly referenceNumber: string;
      readonly title: string;
      readonly purpose: string;
      readonly beginDate: string;
      readonly endDate: string;
      readonly requestedBy: { readonly user: { readonly name: string } };
    },
    request: CreateInSituVisitReportRequest,
    suffix: string,
  ): InSituVisitReportDetail {
    const requestedObject: InSituVisitReportEvidenceItem = {
      id: `mock-requested-object-${suffix}`,
      sourceId: project.referenceNumber,
      description: project.title,
      position: 0,
      attachments: [],
    };
    const record: InSituVisitRecord = {
      id: report.inSituVisitRecordId,
      code: `CUP-${suffix}`,
      visitBeginDate: project.beginDate,
      visitEndDate: project.endDate,
      visitorName: project.requestedBy.user.name,
      placeName: 'MUHNAC',
      generatedAt: report.createdAt,
      recordSchemaVersion: 2,
      sourceProjectId: report.projectId,
      sourceProjectTitle: project.title,
      sourceProjectPurpose: project.purpose,
      plannedBeginDate: project.beginDate,
      plannedEndDate: project.endDate,
      executionEvidenceType: 'project_completed',
      executionOccurredAt: report.createdAt,
      executionRecordedBy: report.createdBy,
      executionEvidenceGaps: [],
      mappingVersion: 'in-situ-visit-cidoc-v2',
      crmVersion: '7.1.3',
      requestedObjects: [requestedObject],
      inSituOccurrences: [],
      inSituLogs: [],
      inSituPublications: [],
    };

    return {
      ...report,
      narrative: {
        narrativeId: report.narrativeId,
        recordId: report.inSituVisitRecordId,
        generatedAt: report.createdAt,
        meta: {
          resolvedNarrativeType: request.narrativeType,
          resolutionSource: 'request',
          targetLanguage: request.targetLanguage,
          creativityTemperature: request.creativityTemperature,
          llmModel: 'llama3.1:8b',
          factsSnapshotId: `mock-facts-${suffix}`,
          promptVersionId: `pver-mock-${request.narrativeType}-v1`,
          promptVersion: `museum-narrative-${request.narrativeType}-v1`,
          modelResponseHash: `sha256:mock-response-${suffix}`,
          validationConforms: true,
          validationFindings: [],
        },
        factsSnapshot: {
          id: `mock-facts-${suffix}`,
          recordId: report.inSituVisitRecordId,
          payloadJson: JSON.stringify({
            project_reference: project.referenceNumber,
            visitor_name: project.requestedBy.user.name,
            requested_objects: [project.title],
            occurrences: [],
            logs: [],
            publications: [],
            evidence_gaps: [],
          }),
          payloadHash: `sha256:mock-facts-${suffix}`,
          builderVersion: 'canonical-visit-facts-v1',
          promptVersion: `museum-narrative-${request.narrativeType}-v1`,
          cidocDocumentJson: JSON.stringify({ '@graph': [{ '@id': `ex:visit/${report.id}` }] }),
          cidocValidationReport: 'Validation Report\nConforms: True',
          cidocConforms: true,
          createdAt: report.createdAt,
        },
        text: `Generated ${request.narrativeType} narrative for ${project.title}. ${project.purpose}`,
      },
      record,
    };
  }

  private fail<T>(status: number, error: string, message: string): Observable<T> {
    return throwError(() => ({ status, error, message }));
  }
}
