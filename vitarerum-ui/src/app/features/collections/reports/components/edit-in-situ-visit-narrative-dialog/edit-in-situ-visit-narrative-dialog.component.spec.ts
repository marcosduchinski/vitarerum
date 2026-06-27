import { TestBed } from '@angular/core/testing';
import { of, throwError } from 'rxjs';

import { InSituVisitReportNarrative } from '../../models/report.model';
import { REPORTS_API_SERVICE } from '../../services/reports-api.service';
import { EditInSituVisitNarrativeDialogComponent } from './edit-in-situ-visit-narrative-dialog.component';

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
  text: 'Original museum narrative.',
};

describe('EditInSituVisitNarrativeDialogComponent', () => {
  const updateNarrative = vi.fn();

  beforeEach(async () => {
    updateNarrative.mockReset();
    updateNarrative.mockReturnValue(of({ ...NARRATIVE, text: 'Corrected museum narrative.' }));
    await TestBed.configureTestingModule({
      imports: [EditInSituVisitNarrativeDialogComponent],
      providers: [
        {
          provide: REPORTS_API_SERVICE,
          useValue: { updateInSituVisitNarrative: updateNarrative },
        },
      ],
    }).compileComponents();
  });

  it('initializes the draft and disables saving until the text changes', () => {
    const fixture = openEditor();
    const element = fixture.nativeElement as HTMLElement;
    const textarea = element.querySelector<HTMLTextAreaElement>('#narrative-editor-text');
    const save = element.querySelector<HTMLButtonElement>('button[type="submit"]');

    expect(textarea?.value).toBe(NARRATIVE.text);
    expect(save?.disabled).toBe(true);
    expect(element.textContent).toContain('No changes');
  });

  it('patches trimmed text and emits the normalized updated narrative', async () => {
    const fixture = openEditor();
    const saved = vi.fn();
    fixture.componentInstance.saved.subscribe(saved);
    setTextarea(fixture, '  Corrected museum narrative.  ');

    const save = (fixture.nativeElement as HTMLElement).querySelector<HTMLButtonElement>(
      'button[type="submit"]',
    );
    expect(save?.disabled).toBe(false);
    save?.click();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(updateNarrative).toHaveBeenCalledWith('record-1', 'narrative-1', {
      narrative: 'Corrected museum narrative.',
    });
    expect(saved).toHaveBeenCalledWith({
      ...NARRATIVE,
      text: 'Corrected museum narrative.',
    });
  });

  it('rejects blank text before issuing a request', () => {
    const fixture = openEditor();
    setTextarea(fixture, '   ');

    const form = (fixture.nativeElement as HTMLElement).querySelector('form');
    form?.dispatchEvent(new SubmitEvent('submit', { bubbles: true, cancelable: true }));
    fixture.detectChanges();

    expect(updateNarrative).not.toHaveBeenCalled();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain(
      'Narrative text cannot be blank.',
    );
  });

  it('preserves the draft and presents the API error when saving fails', async () => {
    updateNarrative.mockReturnValue(
      throwError(() => ({ status: 503, error: 'MODEL_UNAVAILABLE', message: 'Unavailable' })),
    );
    const fixture = openEditor();
    setTextarea(fixture, 'A correction that must be preserved.');

    (fixture.nativeElement as HTMLElement)
      .querySelector<HTMLButtonElement>('button[type="submit"]')
      ?.click();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(
      (fixture.nativeElement as HTMLElement).querySelector<HTMLTextAreaElement>(
        '#narrative-editor-text',
      )?.value,
    ).toBe('A correction that must be preserved.');
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('Unexpected error');
  });

  it('requires explicit confirmation before discarding a changed draft', () => {
    const fixture = openEditor();
    const closed = vi.fn();
    fixture.componentInstance.closed.subscribe(closed);
    setTextarea(fixture, 'Unsaved correction.');

    (fixture.nativeElement as HTMLElement)
      .querySelector<HTMLButtonElement>('[aria-label="Close narrative editor"]')
      ?.click();
    fixture.detectChanges();

    expect(closed).not.toHaveBeenCalled();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain(
      'Discard this correction?',
    );

    const discard = Array.from(
      (fixture.nativeElement as HTMLElement).querySelectorAll<HTMLButtonElement>('button'),
    ).find((button) => button.textContent?.includes('Discard changes'));
    discard?.click();

    expect(closed).toHaveBeenCalledOnce();
  });

  function openEditor() {
    const fixture = TestBed.createComponent(EditInSituVisitNarrativeDialogComponent);
    fixture.componentRef.setInput('narrative', NARRATIVE);
    fixture.componentRef.setInput('open', true);
    fixture.detectChanges();
    return fixture;
  }

  function setTextarea(fixture: ReturnType<typeof openEditor>, value: string): void {
    const textarea = (fixture.nativeElement as HTMLElement).querySelector<HTMLTextAreaElement>(
      '#narrative-editor-text',
    );
    if (!textarea) throw new Error('Narrative textarea not found');
    textarea.value = value;
    textarea.dispatchEvent(new Event('input', { bubbles: true }));
    fixture.detectChanges();
  }
});
