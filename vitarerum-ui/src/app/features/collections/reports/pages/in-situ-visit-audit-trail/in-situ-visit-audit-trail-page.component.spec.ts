import { HttpErrorResponse } from '@angular/common/http';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { Observable, of, throwError } from 'rxjs';

import { InSituVisitReportAuditTrail } from '../../models/report.model';
import { REPORTS_API_SERVICE } from '../../services/reports-api.service';
import { InSituVisitAuditTrailPageComponent } from './in-situ-visit-audit-trail-page.component';

const AUDIT: InSituVisitReportAuditTrail = {
  id: 'report-1',
  createdAt: '2026-06-22T10:30:00Z',
  createdBy: 'permission-1',
  projectId: 'project-1',
  narrativeId: 'narrative-1',
  inSituVisitRecordId: 'record-1',
  record: {
    id: 'record-1',
    code: 'CUP-ABCD1234',
    visitBeginDate: '2026-06-01',
    visitEndDate: '2026-06-03',
    visitorName: 'Maria do Rosário',
    placeName: 'Museum',
    generatedAt: '2026-06-22T10:30:00Z',
    recordSchemaVersion: 2,
    mappingVersion: 'in-situ-visit-cidoc-v2',
    crmVersion: '7.1.3',
    requestedObjects: [
      { id: 'object-1', sourceId: 'INV-1', description: 'Vase', position: 0, attachments: [] },
    ],
    inSituOccurrences: [],
    inSituLogs: [],
    inSituPublications: [],
  },
  narrative: {
    narrativeId: 'narrative-1',
    recordId: 'record-1',
    generatedAt: '2026-06-22T10:30:00Z',
    meta: {
      resolvedNarrativeType: 'institutional',
      resolutionSource: 'default',
      targetLanguage: 'pt',
      creativityTemperature: 0.3,
      llmModel: 'llama3.1:8b',
      factsSnapshotId: 'facts-1',
      promptVersionId: 'pver-insitu-institutional-v1',
      promptVersion: 'museum-narrative-institutional-v1',
      modelResponseHash: 'sha256:narrative',
      validationConforms: true,
      validationFindings: [],
    },
    factsSnapshot: null,
    text: 'Current narrative text.',
  },
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
    payloadJson: '{"project_reference":"CUP-ABCD1234","evidence_gaps":[]}',
    payloadHash: 'sha256:facts',
    builderVersion: 'canonical-visit-facts-v1',
    promptVersion: 'museum-narrative-institutional-v1',
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
    promptVersionId: 'pver-insitu-institutional-v1',
    promptVersion: 'museum-narrative-institutional-v1',
    responseHash: 'sha256:narrative',
  },
  validation: { conforms: true, findings: [] },
  revisions: {
    content: [
      {
        id: 'revision-1',
        narrativeId: 'narrative-1',
        recordId: 'record-1',
        previousNarrative: 'Original narrative text.',
        revisedNarrative: 'Current narrative text.',
        editedBy: 'permission-1',
        editedAt: '2026-06-22T11:00:00Z',
      },
    ],
    page: 0,
    size: 100,
    totalElements: 1,
    totalPages: 1,
  },
};

class ReportsApiServiceStub {
  readonly calls: { projectId: string; reportId: string }[] = [];
  response: Observable<InSituVisitReportAuditTrail> = of(AUDIT);

  getInSituVisitReportAuditTrail(projectId: string, reportId: string) {
    this.calls.push({ projectId, reportId });
    return this.response;
  }
}

describe('InSituVisitAuditTrailPageComponent', () => {
  let reportsService: ReportsApiServiceStub;

  beforeEach(async () => {
    reportsService = new ReportsApiServiceStub();
    await TestBed.configureTestingModule({
      imports: [InSituVisitAuditTrailPageComponent],
      providers: [provideRouter([]), { provide: REPORTS_API_SERVICE, useValue: reportsService }],
    }).compileComponents();
  });

  async function render(): Promise<HTMLElement> {
    const fixture = TestBed.createComponent(InSituVisitAuditTrailPageComponent);
    fixture.componentRef.setInput('projectId', 'project-1');
    fixture.componentRef.setInput('reportId', 'report-1');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  it('loads the audit trail and renders the production stages', async () => {
    const compiled = await render();

    expect(reportsService.calls).toEqual([{ projectId: 'project-1', reportId: 'report-1' }]);
    expect(compiled.textContent).toContain('Audit trail');
    expect(compiled.textContent).toContain('CUP-ABCD1234');
    expect(compiled.textContent).toContain('Execution and approval');
    expect(compiled.textContent).toContain('CIDOC-CRM and SHACL');
    expect(compiled.textContent).toContain('Facts used in narrative');
    expect(compiled.textContent).toContain('Generation');
    expect(compiled.textContent).toContain('Validation findings');
    expect(compiled.textContent).toContain('Revisions');
    expect(compiled.textContent).toContain('Missing publication link.');
    expect(compiled.textContent).toContain('sha256:narrative');
    expect(compiled.textContent).toContain('Original narrative text.');
    expect(compiled.querySelectorAll('.audit-finding-mark')).toHaveLength(0);
    expect(
      compiled.querySelector<HTMLAnchorElement>('.audit-trail__report-link')?.getAttribute('href'),
    ).toBe('/p/collections/reports/visits-in-situ/project-1/report-1');
  });

  it('links only the generation prompt version to the exact prompt version', async () => {
    const compiled = await render();
    const promptLinks = Array.from(compiled.querySelectorAll<HTMLAnchorElement>('.audit-link'));

    expect(promptLinks).toHaveLength(1);
    expect(promptLinks[0]?.textContent?.trim()).toBe('museum-narrative-institutional-v1');
    expect(promptLinks[0]?.getAttribute('href')).toBe(
      '/p/ai/prompts/versions/pver-insitu-institutional-v1',
    );

    const factsStage = compiled
      .querySelector<HTMLElement>('#audit-facts-heading')
      ?.closest('section');
    expect(factsStage?.textContent).toContain('museum-narrative-institutional-v1');
    expect(factsStage?.querySelector('.audit-link')).toBeNull();
  });

  it('keeps a legacy prompt version textual when no prompt version id exists', async () => {
    reportsService.response = of({
      ...AUDIT,
      generation: {
        ...AUDIT.generation,
        promptVersionId: null,
      },
    });

    const compiled = await render();

    expect(compiled.textContent).toContain('museum-narrative-institutional-v1');
    expect(compiled.querySelector('.audit-link')).toBeNull();
  });

  it('highlights findings only in the original generated narrative and escapes HTML', async () => {
    reportsService.response = of({
      ...AUDIT,
      narrative: {
        ...AUDIT.narrative!,
        text: 'Current narrative still mentions 2027-05-01.',
      },
      validation: {
        conforms: false,
        findings: [
          {
            code: 'invented_date',
            message: 'Invented <date> & not in source',
            evidence: '2027-05-01',
          },
        ],
      },
      revisions: {
        ...AUDIT.revisions!,
        content: [
          {
            ...AUDIT.revisions!.content[0],
            previousNarrative:
              'Original <b>unsafe</b> narrative mentions 2027-05-01 & repeats 2027-05-01.',
            revisedNarrative: 'Current narrative still mentions 2027-05-01.',
          },
        ],
      },
    });

    const compiled = await render();
    const original = compiled.querySelector<HTMLElement>(
      '.audit-narrative:not(.audit-narrative--current)',
    );
    const current = compiled.querySelector<HTMLElement>('.audit-narrative--current');
    const marks = original?.querySelectorAll<HTMLElement>('.audit-finding-mark') ?? [];

    expect(marks).toHaveLength(2);
    expect(marks[0]?.textContent).toBe('2027-05-01');
    expect(marks[0]?.getAttribute('title')).toBe('Invented <date> & not in source');
    expect(original?.innerHTML).toContain('&lt;b&gt;unsafe&lt;/b&gt;');
    expect(original?.innerHTML).not.toContain('<b>unsafe</b>');
    expect(current?.textContent).toContain('Current narrative still mentions 2027-05-01.');
    expect(current?.querySelector('.audit-finding-mark')).toBeNull();
  });

  it('renders API errors from the audit resource', async () => {
    reportsService.response = throwError(
      () =>
        new HttpErrorResponse({
          status: 404,
          error: { error: 'REPORT_NOT_FOUND', message: 'Report not found' },
        }),
    );

    const compiled = await render();

    expect(compiled.textContent).toContain('Not found');
    expect(compiled.textContent).toContain('The requested resource no longer exists.');
  });
});
