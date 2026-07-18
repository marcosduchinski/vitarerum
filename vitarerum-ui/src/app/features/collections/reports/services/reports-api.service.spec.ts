import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { API_BASE_URL } from '@core/config/app-config.model';

import {
  CidocCrmJsonObject,
  InSituVisitReport,
  InSituVisitReportAuditTrail,
  InSituVisitReportDetail,
} from '../models/report.model';
import { ReportsApiService } from './reports-api.service';

describe('ReportsApiService', () => {
  let service: ReportsApiService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: API_BASE_URL, useValue: 'https://api.example.test' },
        ReportsApiService,
      ],
    });

    service = TestBed.inject(ReportsApiService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    http.verify();
  });

  it('lists in-situ visit reports with pagination', () => {
    let receivedCode: string | null = null;
    service
      .listInSituVisitReports({ page: 2, size: 25 })
      .subscribe((page) => (receivedCode = page.content[0]?.code ?? null));

    const request = http.expectOne(
      (candidate) =>
        candidate.url === 'https://api.example.test/reports/collection-use/in_situ_visit',
    );

    expect(request.request.method).toBe('GET');
    expect(request.request.params.get('page')).toBe('2');
    expect(request.request.params.get('size')).toBe('25');
    request.flush({
      content: [
        {
          id: 'report-1',
          createdAt: '2026-06-22T10:30:00Z',
          createdBy: 'permission-1',
          projectId: 'project-1',
          narrativeId: 'narrative-1',
          inSituVisitRecordId: 'record-1',
          code: 'CUP-ABCD1234',
          visitorName: 'Maria do Rosário',
          placeName: 'Museum',
          visitBeginDate: '2026-06-01',
          visitEndDate: '2026-06-03',
        },
      ],
      page: 2,
      size: 25,
      totalElements: 1,
      totalPages: 3,
    });
    expect(receivedCode).toBe('CUP-ABCD1234');
  });

  it('loads and normalizes an in-situ visit report detail', () => {
    let received: InSituVisitReportDetail | null = null;
    service
      .getInSituVisitReportDetail('project-1', 'report-1')
      .subscribe((detail) => (received = detail));

    const request = http.expectOne(
      'https://api.example.test/reports/collection-use/project-1/in_situ_visit/report-1/detail',
    );
    expect(request.request.method).toBe('GET');
    request.flush({
      id: 'report-1',
      createdAt: '2026-06-22T10:30:00Z',
      createdBy: 'permission-1',
      projectId: 'project-1',
      narrativeId: 'narrative-1',
      inSituVisitRecordId: 'record-1',
      narrative: {
        narrative_id: 'narrative-1',
        record_id: 'record-1',
        generated_at: '2026-06-22T10:30:00Z',
        meta: {
          resolved_narrative_type: 'institutional',
          resolution_source: 'default',
          target_language: 'pt',
          creativity_temperature: 0.3,
          llm_model: 'llama3.1:8b',
          facts_snapshot_id: 'facts-1',
          prompt_version: 'museum-narrative-canonical-v1',
          model_response_hash: 'sha256:narrative',
          validation_conforms: true,
          validation_findings: [],
        },
        data: { narrative: 'A museum narrative.' },
        facts_snapshot: {
          id: 'facts-1',
          record_id: 'record-1',
          payload_json: '{"project_reference":"CUP-ABCD1234"}',
          payload_hash: 'sha256:facts',
          builder_version: 'canonical-visit-facts-v1',
          prompt_version: 'museum-narrative-canonical-v1',
          cidoc_document_json: '{"@graph":[]}',
          cidoc_validation_report: 'Validation Report\nConforms: True',
          cidoc_conforms: true,
          created_at: '2026-06-22T10:30:00Z',
        },
      },
      record: {
        id: 'record-1',
        code: 'CUP-ABCD1234',
        visitBeginDate: '2026-06-01',
        visitEndDate: '2026-06-03',
        visitorName: 'Maria do Rosário',
        placeName: 'Museum',
        generatedAt: '2026-06-22T10:30:00Z',
        recordSchemaVersion: 2,
        sourceProjectId: 'project-1',
        sourceProjectTitle: 'Research visit',
        plannedBeginDate: '2026-06-01',
        plannedEndDate: '2026-06-03',
        executionEvidenceType: 'project_completed',
        executionOccurredAt: '2026-06-03T16:30:00Z',
        executionRecordedBy: 'permission-1',
        executionEvidenceGaps: ['No access-log conclusion date was recorded.'],
        mappingVersion: 'in-situ-visit-cidoc-v2',
        crmVersion: '7.1.3',
        requestedObjects: [
          {
            id: 'object-1',
            sourceId: 'INV-1',
            description: 'Requested specimen',
            position: 0,
          },
        ],
        inSituOccurrences: [
          {
            id: 'occurrence-1',
            sourceId: 'OCC-1',
            description: 'Observed condition',
            position: 0,
            attachments: [
              {
                id: 'attachment-1',
                sourceId: 'ATT-1',
                description: 'Photo',
                reference: 'https://files.example.test/photo.jpg',
                position: 0,
              },
            ],
          },
        ],
        inSituLogs: [],
        inSituPublications: [],
      },
    });

    expect(received).toMatchObject({
      id: 'report-1',
      narrative: {
        narrativeId: 'narrative-1',
        recordId: 'record-1',
        text: 'A museum narrative.',
        meta: {
          resolvedNarrativeType: 'institutional',
          targetLanguage: 'pt',
          creativityTemperature: 0.3,
          llmModel: 'llama3.1:8b',
          factsSnapshotId: 'facts-1',
          promptVersion: 'museum-narrative-canonical-v1',
          validationConforms: true,
        },
        factsSnapshot: {
          builderVersion: 'canonical-visit-facts-v1',
          payloadHash: 'sha256:facts',
          cidocDocumentJson: '{"@graph":[]}',
          cidocConforms: true,
        },
      },
      record: {
        code: 'CUP-ABCD1234',
        recordSchemaVersion: 2,
        executionEvidenceType: 'project_completed',
        executionEvidenceGaps: ['No access-log conclusion date was recorded.'],
        mappingVersion: 'in-situ-visit-cidoc-v2',
        crmVersion: '7.1.3',
        requestedObjects: [{ sourceId: 'INV-1', attachments: [] }],
        inSituOccurrences: [
          {
            sourceId: 'OCC-1',
            attachments: [{ reference: 'https://files.example.test/photo.jpg' }],
          },
        ],
      },
    });
  });

  it('preserves nullable detail artifacts', () => {
    let received: InSituVisitReportDetail | null = null;
    service
      .getInSituVisitReportDetail('project-1', 'report-1')
      .subscribe((detail) => (received = detail));

    const request = http.expectOne(
      'https://api.example.test/reports/collection-use/project-1/in_situ_visit/report-1/detail',
    );
    request.flush({
      id: 'report-1',
      createdAt: '2026-06-22T10:30:00Z',
      createdBy: 'permission-1',
      projectId: 'project-1',
      narrativeId: 'narrative-1',
      inSituVisitRecordId: 'record-1',
      narrative: null,
      record: null,
    });

    expect(received).toMatchObject({ narrative: null, record: null });
  });

  it('loads and normalizes an in-situ visit report audit trail', () => {
    let received: InSituVisitReportAuditTrail | null = null;

    service
      .getInSituVisitReportAuditTrail('project-1', 'report-1')
      .subscribe((audit) => (received = audit));

    const request = http.expectOne(
      'https://api.example.test/reports/collection-use/project-1/in_situ_visit/report-1/audit-trail',
    );
    expect(request.request.method).toBe('GET');
    request.flush({
      id: 'report-1',
      createdAt: '2026-06-22T10:30:00Z',
      createdBy: 'permission-1',
      projectId: 'project-1',
      narrativeId: 'narrative-1',
      inSituVisitRecordId: 'record-1',
      record: null,
      narrative: null,
      evidence: {
        recordId: 'record-1',
        projectId: 'project-1',
        code: 'CUP-ABCD1234',
        executionEvidenceType: 'project_completed',
        executionOccurredAt: '2026-06-03T16:30:00Z',
        executionRecordedBy: 'permission-1',
        executionEvidenceGaps: ['Missing publication link.'],
        approvedAt: null,
        approvedBy: null,
        approvalNote: null,
      },
      cidoc: {
        documentJson: '{"@graph":[]}',
        mappingVersion: 'in-situ-visit-cidoc-v2',
        crmVersion: '7.1.3',
        recordSchemaVersion: 2,
        conforms: true,
        validationReport: 'Validation Report\nConforms: True',
      },
      facts: {
        snapshotId: 'facts-1',
        payloadJson: '{"project_reference":"CUP-ABCD1234"}',
        payloadHash: 'sha256:facts',
        builderVersion: 'canonical-visit-facts-v1',
        promptVersion: 'museum-narrative-canonical-v1',
        createdAt: '2026-06-22T10:30:00Z',
      },
      generation: {
        narrativeId: 'narrative-1',
        generatedAt: '2026-06-22T10:30:00Z',
        narrativeType: 'institutional',
        resolutionSource: 'default',
        targetLanguage: 'pt',
        creativityTemperature: 0.3,
        llmModel: 'llama3.1:8b',
        promptVersion: 'museum-narrative-canonical-v1',
        responseHash: 'sha256:narrative',
      },
      validation: {
        conforms: true,
        findings: [],
      },
      revisions: {
        content: [
          {
            id: 'revision-1',
            narrative_id: 'narrative-1',
            record_id: 'record-1',
            previous_narrative: 'Before.',
            revised_narrative: 'After.',
            edited_by: 'permission-1',
            edited_at: '2026-06-22T11:00:00Z',
          },
        ],
        page: 0,
        size: 100,
        total_elements: 1,
        total_pages: 1,
      },
    });

    expect(received).toMatchObject({
      id: 'report-1',
      evidence: { code: 'CUP-ABCD1234', executionEvidenceGaps: ['Missing publication link.'] },
      cidoc: { documentJson: '{"@graph":[]}', conforms: true },
      facts: { snapshotId: 'facts-1', payloadHash: 'sha256:facts' },
      generation: { responseHash: 'sha256:narrative' },
      revisions: {
        totalElements: 1,
        content: [
          {
            previousNarrative: 'Before.',
            revisedNarrative: 'After.',
            editedBy: 'permission-1',
          },
        ],
      },
    });
  });

  it('loads the CIDOC-CRM JSON-LD document for an in-situ visit record', () => {
    let received: CidocCrmJsonObject | null = null;
    service.getInSituVisitCidocCrm('record-1').subscribe((document) => (received = document));

    const request = http.expectOne(
      'https://api.example.test/cidoc-mapping/in-situ-visit/record-1/cidoc-crm',
    );
    expect(request.request.method).toBe('GET');

    const document = {
      '@context': { crm: 'http://www.cidoc-crm.org/cidoc-crm/' },
      '@graph': [{ '@id': 'ex:visit/record-1', '@type': 'crm:E7_Activity' }],
    };
    request.flush(document);

    expect(received).toEqual(document);
  });

  it('updates and normalizes an in-situ visit narrative', () => {
    let receivedText: string | null = null;
    service
      .updateInSituVisitNarrative('record-1', 'narrative-1', {
        narrative: 'Corrected narrative text.',
      })
      .subscribe((narrative) => (receivedText = narrative.text));

    const request = http.expectOne(
      'https://api.example.test/cidoc-mapping/in-situ-visit/record-1/narratives/narrative-1',
    );
    expect(request.request.method).toBe('PATCH');
    expect(request.request.body).toEqual({ narrative: 'Corrected narrative text.' });
    request.flush({
      narrative_id: 'narrative-1',
      record_id: 'record-1',
      generated_at: '2026-06-22T10:30:00Z',
      meta: {
        resolved_narrative_type: 'institutional',
        resolution_source: 'default',
        target_language: 'pt',
        creativity_temperature: 0.3,
        llm_model: 'llama3.1:8b',
      },
      data: { narrative: 'Corrected narrative text.' },
    });

    expect(receivedText).toBe('Corrected narrative text.');
  });

  it('creates an in-situ visit report with the contract wire format', () => {
    const response = {
      id: 'report-1',
      createdAt: '2026-06-22T10:30:00Z',
      createdBy: 'permission-1',
      projectId: 'project-1',
      narrativeId: 'narrative-1',
      inSituVisitRecordId: 'record-1',
    };
    let received: InSituVisitReport | null = null;

    service
      .createInSituVisitReport('project-1', {
        targetLanguage: 'pt',
        narrativeType: 'institutional',
        creativityTemperature: 0.3,
      })
      .subscribe((value) => (received = value));

    const request = http.expectOne(
      'https://api.example.test/reports/collection-use/project-1/in_situ_visit',
    );
    expect(request.request.method).toBe('POST');
    expect(request.request.body).toEqual({
      target_language: 'pt',
      narrative_type: 'institutional',
      creativity_temperature: 0.3,
    });

    request.flush(response, {
      status: 201,
      statusText: 'Created',
      headers: {
        Location: '/api/v1/reports/collection-use/project-1/in_situ_visit/report-1',
      },
    });
    expect(received).toEqual(response);
  });
});
