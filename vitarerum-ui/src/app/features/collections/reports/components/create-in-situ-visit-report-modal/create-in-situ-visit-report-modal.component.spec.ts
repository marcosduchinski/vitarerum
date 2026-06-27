import { ComponentRef } from '@angular/core';
import { TestBed } from '@angular/core/testing';

import { CreateInSituVisitReportRequest } from '../../models/report.model';
import { CreateInSituVisitReportModalComponent } from './create-in-situ-visit-report-modal.component';

describe('CreateInSituVisitReportModalComponent', () => {
  let componentRef: ComponentRef<CreateInSituVisitReportModalComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [CreateInSituVisitReportModalComponent],
    }).compileComponents();
  });

  function render(): HTMLElement {
    const fixture = TestBed.createComponent(CreateInSituVisitReportModalComponent);
    componentRef = fixture.componentRef;
    componentRef.setInput('open', true);
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  it('shows the supported generation options and defaults', () => {
    const compiled = render();

    expect(selectById(compiled, 'report-target-language').value).toBe('pt');
    expect(selectById(compiled, 'report-narrative-type').value).toBe('institutional');
    expect(inputById(compiled, 'report-creativity').value).toBe('0.3');
    expect(compiled.textContent).toContain('Portuguese');
    expect(compiled.textContent).toContain('English');
    expect(compiled.textContent).toContain('Social media');
  });

  it('emits the selected request', () => {
    const compiled = render();
    const submitted: CreateInSituVisitReportRequest[] = [];
    componentRef.instance.submitted.subscribe((request) => submitted.push(request));

    changeSelect(selectById(compiled, 'report-target-language'), 'en');
    changeSelect(selectById(compiled, 'report-narrative-type'), 'social_media');
    changeInput(inputById(compiled, 'report-creativity'), '0.8');
    componentRef.changeDetectorRef.detectChanges();
    buttonByText(compiled, 'Create report').click();

    expect(submitted).toEqual([
      {
        targetLanguage: 'en',
        narrativeType: 'social_media',
        creativityTemperature: 0.8,
      },
    ]);
  });

  it('emits cancellation without submitting', () => {
    const compiled = render();
    let cancelled = false;
    const submitted: CreateInSituVisitReportRequest[] = [];
    componentRef.instance.cancelled.subscribe(() => (cancelled = true));
    componentRef.instance.submitted.subscribe((request) => submitted.push(request));

    buttonByText(compiled, 'Cancel').click();

    expect(cancelled).toBe(true);
    expect(submitted).toEqual([]);
  });
});

function selectById(root: HTMLElement, id: string): HTMLSelectElement {
  const element = root.querySelector<HTMLSelectElement>(`#${id}`);
  expect(element).not.toBeNull();
  return element!;
}

function inputById(root: HTMLElement, id: string): HTMLInputElement {
  const element = root.querySelector<HTMLInputElement>(`#${id}`);
  expect(element).not.toBeNull();
  return element!;
}

function buttonByText(root: HTMLElement, text: string): HTMLButtonElement {
  const element = Array.from(root.querySelectorAll<HTMLButtonElement>('button')).find((button) =>
    button.textContent?.includes(text),
  );
  expect(element).not.toBeNull();
  return element!;
}

function changeSelect(element: HTMLSelectElement, value: string): void {
  element.value = value;
  element.dispatchEvent(new Event('input', { bubbles: true }));
}

function changeInput(element: HTMLInputElement, value: string): void {
  element.value = value;
  element.dispatchEvent(new Event('input', { bubbles: true }));
}
