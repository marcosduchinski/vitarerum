import { TestBed } from '@angular/core/testing';

import { InSituVisitReportNarrative } from '../../models/report.model';
import { InSituVisitReportNarrativeComponent } from './in-situ-visit-report-narrative.component';

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
  text: 'A narrative about the documented museum visit.',
};

describe('InSituVisitReportNarrativeComponent', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [InSituVisitReportNarrativeComponent],
    }).compileComponents();
  });

  it('renders the narrative text and an authorship byline', () => {
    const fixture = TestBed.createComponent(InSituVisitReportNarrativeComponent);
    fixture.componentRef.setInput('narrative', NARRATIVE);
    fixture.detectChanges();

    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(text).toContain('A narrative about the documented museum visit.');
    // The byline credits the model and narrative type; full provenance lives in the rail.
    expect(text).toContain('llama3.1:8b');
    expect(text).toContain('institutional');
  });

  it('renders an explicit unavailable state', () => {
    const fixture = TestBed.createComponent(InSituVisitReportNarrativeComponent);
    fixture.componentRef.setInput('narrative', null);
    fixture.detectChanges();

    expect((fixture.nativeElement as HTMLElement).textContent).toContain(
      'The narrative artifact is unavailable',
    );
  });

  it('renders accessible view and edit actions and emits their typed payloads', () => {
    const fixture = TestBed.createComponent(InSituVisitReportNarrativeComponent);
    const viewRequested = vi.fn();
    const editRequested = vi.fn();
    fixture.componentRef.setInput('narrative', NARRATIVE);
    fixture.componentInstance.viewCidocCrm.subscribe(viewRequested);
    fixture.componentInstance.editNarrative.subscribe(editRequested);
    fixture.detectChanges();

    const element = fixture.nativeElement as HTMLElement;
    const viewButton = element.querySelector<HTMLButtonElement>(
      'button[aria-label="View CIDOC-CRM data"]',
    );
    const editButton = element.querySelector<HTMLButtonElement>(
      'button[aria-label="Edit narrative"]',
    );

    expect(viewButton?.disabled).toBe(false);
    expect(editButton?.disabled).toBe(false);
    viewButton?.click();
    editButton?.click();

    expect(viewRequested).toHaveBeenCalledWith('record-1');
    expect(editRequested).toHaveBeenCalledWith(NARRATIVE);
  });

  it('keeps CIDOC viewing available for a record when the narrative is unavailable', () => {
    const fixture = TestBed.createComponent(InSituVisitReportNarrativeComponent);
    fixture.componentRef.setInput('recordId', 'record-1');
    fixture.componentRef.setInput('narrative', null);
    fixture.detectChanges();

    const element = fixture.nativeElement as HTMLElement;
    expect(
      element.querySelector<HTMLButtonElement>('button[aria-label="View CIDOC-CRM data"]')
        ?.disabled,
    ).toBe(false);
    expect(
      element.querySelector<HTMLButtonElement>('button[aria-label="Edit narrative"]')?.disabled,
    ).toBe(true);
  });
});
