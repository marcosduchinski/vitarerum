import { HttpErrorResponse } from '@angular/common/http';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { Observable, of, throwError } from 'rxjs';

import {
  InSituVisitReportDetail,
  InSituVisitReportNarrative,
  UpdateInSituVisitNarrativeRequest,
} from '../../models/report.model';
import { REPORTS_API_SERVICE } from '../../services/reports-api.service';
import { InSituVisitReportDetailPageComponent } from './in-situ-visit-report-detail-page.component';

const DETAIL: InSituVisitReportDetail = {
  id: 'report-1',
  createdAt: '2026-06-22T10:30:00Z',
  createdBy: 'permission-1',
  projectId: 'project-1',
  narrativeId: 'narrative-1',
  inSituVisitRecordId: 'record-1',
  narrative: {
    narrativeId: 'narrative-1',
    recordId: 'record-1',
    generatedAt: '2026-06-22T10:30:00Z',
    meta: {
      resolvedNarrativeType: 'institutional',
      resolutionSource: 'request',
      targetLanguage: 'pt',
      creativityTemperature: 0.3,
      llmModel: 'llama3.1:8b',
      factsSnapshotId: 'facts-1',
      promptVersionId: 'pver-insitu-institutional-v1',
      promptVersion: 'museum-narrative-institutional-v1',
      validationConforms: true,
      validationFindings: [],
    },
    factsSnapshot: {
      id: 'facts-1',
      recordId: 'record-1',
      payloadJson: '{"project_reference":"CUP-ABCD1234","visitor_name":"Maria do Rosário"}',
      payloadHash: 'sha256:facts',
      builderVersion: 'canonical-visit-facts-v1',
      promptVersion: 'museum-narrative-institutional-v1',
      cidocDocumentJson: '{"@graph":[]}',
      cidocValidationReport: 'Validation Report\nConforms: True',
      cidocConforms: true,
      createdAt: '2026-06-22T10:30:00Z',
    },
    text: 'The generated report narrative.',
  },
  record: {
    id: 'record-1',
    code: 'CUP-ABCD1234',
    visitBeginDate: '2026-06-01',
    visitEndDate: '2026-06-03',
    visitorName: 'Maria do Rosário',
    placeName: 'Museum',
    generatedAt: '2026-06-22T10:30:00Z',
    mappingVersion: 'in-situ-visit-cidoc-v2',
    crmVersion: '7.1.3',
    requestedObjects: [
      {
        id: 'object-1',
        sourceId: 'INV-1',
        description: 'Requested vase',
        position: 0,
        attachments: [],
      },
    ],
    inSituOccurrences: [],
    inSituLogs: [],
    inSituPublications: [],
  },
};

class ReportsApiServiceStub {
  readonly calls: { projectId: string; reportId: string }[] = [];
  readonly updateCalls: {
    recordId: string;
    narrativeId: string;
    request: UpdateInSituVisitNarrativeRequest;
  }[] = [];
  response: Observable<InSituVisitReportDetail> = of(DETAIL);

  getInSituVisitReportDetail(projectId: string, reportId: string) {
    this.calls.push({ projectId, reportId });
    return this.response;
  }

  updateInSituVisitNarrative(
    recordId: string,
    narrativeId: string,
    request: UpdateInSituVisitNarrativeRequest,
  ) {
    this.updateCalls.push({ recordId, narrativeId, request });
    return of<InSituVisitReportNarrative>({
      ...DETAIL.narrative!,
      text: request.narrative,
    });
  }
}

describe('InSituVisitReportDetailPageComponent', () => {
  let reportsService: ReportsApiServiceStub;

  beforeEach(async () => {
    reportsService = new ReportsApiServiceStub();
    await TestBed.configureTestingModule({
      imports: [InSituVisitReportDetailPageComponent],
      providers: [provideRouter([]), { provide: REPORTS_API_SERVICE, useValue: reportsService }],
    }).compileComponents();
  });

  async function render(): Promise<HTMLElement> {
    const fixture = TestBed.createComponent(InSituVisitReportDetailPageComponent);
    fixture.componentRef.setInput('projectId', 'project-1');
    fixture.componentRef.setInput('reportId', 'report-1');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  it('loads the owned report and renders its dossier masthead and narrative', async () => {
    const compiled = await render();

    expect(reportsService.calls).toEqual([{ projectId: 'project-1', reportId: 'report-1' }]);
    // The visitor headlines the report; the catalog code is demoted to the eyebrow.
    expect(compiled.querySelector('h1')?.textContent).toContain('Maria do Rosário');
    expect(compiled.querySelector('.report-detail__code')?.textContent).toContain('CUP-ABCD1234');
    expect(compiled.textContent).toContain('The generated report narrative.');
    expect(compiled.textContent).toContain('institutional · pt · Generated');
    expect(compiled.textContent).toContain('Conforms');
    expect(compiled.textContent).not.toContain('Facts used in narrative');
    expect(compiled.textContent).not.toContain('canonical-visit-facts-v1');
    expect(compiled.textContent).not.toContain('"project_reference": "CUP-ABCD1234"');
    expect(compiled.textContent).not.toContain('Technical references');
    expect(
      compiled.querySelector<HTMLAnchorElement>('.report-detail__back')?.getAttribute('href'),
    ).toBe('/p/collections/reports/visits-in-situ');
    expect(
      compiled
        .querySelector<HTMLAnchorElement>('a[aria-label="View audit trail"]')
        ?.getAttribute('href'),
    ).toBe('/p/collections/reports/visits-in-situ/project-1/report-1/audit-trail');
  });

  it('renders API errors from the detail resource', async () => {
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

  it('exports only the simple report content without audit artifacts', async () => {
    const createObjectURL = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:report');
    const revokeObjectURL = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined);
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, 'click')
      .mockImplementation(() => undefined);
    const fixture = TestBed.createComponent(InSituVisitReportDetailPageComponent);
    fixture.componentRef.setInput('projectId', 'project-1');
    fixture.componentRef.setInput('reportId', 'report-1');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    (fixture.nativeElement as HTMLElement)
      .querySelector<HTMLButtonElement>('.report-action--primary')
      ?.click();

    expect(createObjectURL).toHaveBeenCalledOnce();
    const blob = createObjectURL.mock.calls[0][0] as Blob;
    const exported = JSON.parse(await blob.text()) as Record<string, unknown>;
    const serialized = JSON.stringify(exported);

    expect(exported['code']).toBe('CUP-ABCD1234');
    expect(serialized).toContain('The generated report narrative.');
    expect(serialized).toContain('Requested vase');
    expect(serialized).not.toContain('factsSnapshot');
    expect(serialized).not.toContain('payloadJson');
    expect(serialized).not.toContain('cidocDocumentJson');
    expect(serialized).not.toContain('cidocValidationReport');
    expect(serialized).not.toContain('validationFindings');
    expect(serialized).not.toContain('promptVersion');
    expect(serialized).not.toContain('modelResponseHash');
    expect(serialized).not.toContain('llmModel');
    expect(serialized).not.toContain('mappingVersion');
    expect(serialized).not.toContain('crmVersion');
    expect(serialized).not.toContain('executionEvidenceGaps');
    expect(click).toHaveBeenCalledOnce();
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:report');

    createObjectURL.mockRestore();
    revokeObjectURL.mockRestore();
    click.mockRestore();
  });

  it('edits the narrative in place while preserving the rest of the report', async () => {
    const fixture = TestBed.createComponent(InSituVisitReportDetailPageComponent);
    fixture.componentRef.setInput('projectId', 'project-1');
    fixture.componentRef.setInput('reportId', 'report-1');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    (fixture.nativeElement as HTMLElement)
      .querySelector<HTMLButtonElement>('[aria-label="Edit narrative"]')
      ?.click();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();

    const textarea = (fixture.nativeElement as HTMLElement).querySelector<HTMLTextAreaElement>(
      '#narrative-editor-text',
    );
    if (!textarea) throw new Error('Narrative editor did not open');
    textarea.value = 'A carefully corrected museum narrative.';
    textarea.dispatchEvent(new Event('input', { bubbles: true }));
    fixture.detectChanges();
    (fixture.nativeElement as HTMLElement)
      .querySelector<HTMLButtonElement>('button[type="submit"]')
      ?.click();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(reportsService.updateCalls).toEqual([
      {
        recordId: 'record-1',
        narrativeId: 'narrative-1',
        request: { narrative: 'A carefully corrected museum narrative.' },
      },
    ]);
    expect((fixture.nativeElement as HTMLElement).textContent).toContain(
      'A carefully corrected museum narrative.',
    );
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('Maria do Rosário');
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('CUP-ABCD1234');
  });
});
