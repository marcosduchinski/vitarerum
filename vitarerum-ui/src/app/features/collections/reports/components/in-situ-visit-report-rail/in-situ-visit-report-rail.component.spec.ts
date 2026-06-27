import { TestBed } from '@angular/core/testing';

import { InSituVisitRecord, InSituVisitReportNarrative } from '../../models/report.model';
import { InSituVisitReportRailComponent } from './in-situ-visit-report-rail.component';

const RECORD: InSituVisitRecord = {
  id: 'record-1',
  code: 'CUP-ABCD1234',
  visitBeginDate: '2026-06-01',
  visitEndDate: '2026-06-03',
  visitorName: 'Maria do Rosário',
  placeName: 'Museum',
  generatedAt: '2026-06-22T10:30:00Z',
  requestedObjects: [
    { id: 'o-1', sourceId: 'INV-1', description: 'Specimen', position: 0, attachments: [] },
    { id: 'o-2', sourceId: 'INV-2', description: 'Specimen', position: 1, attachments: [] },
  ],
  inSituOccurrences: [
    { id: 'c-1', sourceId: 'OCC-1', description: 'Event', position: 0, attachments: [] },
  ],
  inSituLogs: [],
  inSituPublications: [],
};

const NARRATIVE: InSituVisitReportNarrative = {
  narrativeId: 'narrative-1',
  recordId: 'record-1',
  generatedAt: '2026-06-22T10:30:00Z',
  meta: {
    resolvedNarrativeType: 'institutional',
    resolutionSource: 'request',
    targetLanguage: 'pt',
    creativityTemperature: 0.3,
    llmModel: 'llama3.1:8b',
  },
  text: 'Narrative.',
};

describe('InSituVisitReportRailComponent', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [InSituVisitReportRailComponent],
    }).compileComponents();
  });

  it('summarises visit identity, evidence totals and provenance', () => {
    const fixture = TestBed.createComponent(InSituVisitReportRailComponent);
    fixture.componentRef.setInput('record', RECORD);
    fixture.componentRef.setInput('narrative', NARRATIVE);
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    const text = compiled.textContent ?? '';

    expect(text).toContain('Maria do Rosário');
    expect(text).toContain('Museum');
    expect(text).toContain('CUP-ABCD1234');
    // Three evidence items across two populated categories.
    expect(compiled.querySelector('.report-rail__sum')?.textContent).toContain('3');
    // Provenance is surfaced here, not in the narrative body.
    expect(text).toContain('institutional');
    expect(text).toContain('llama3.1:8b');
  });

  it('renders nothing when no record or narrative is supplied', () => {
    const fixture = TestBed.createComponent(InSituVisitReportRailComponent);
    fixture.detectChanges();

    const compiled = fixture.nativeElement as HTMLElement;
    expect(compiled.querySelectorAll('.report-rail__block')).toHaveLength(0);
  });
});
