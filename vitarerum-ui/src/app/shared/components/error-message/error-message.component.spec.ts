import { ChangeDetectionStrategy, Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { ApiError } from '@core/http/api-error.model';

import { ErrorMessageComponent } from './error-message.component';

@Component({
  standalone: true,
  imports: [ErrorMessageComponent],
  template: `
    <app-error-message
      title="Could not load proposals"
      message="Try again in a moment."
      tone="warning"
    />
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
class PlainHostComponent {}

@Component({
  standalone: true,
  imports: [ErrorMessageComponent],
  template: `<app-error-message [apiError]="error" (retry)="retried = true" />`,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
class ApiErrorHostComponent {
  error: ApiError | null = null;
  retried = false;
}

describe('ErrorMessageComponent', () => {
  it('renders alert content with the selected tone', async () => {
    await TestBed.configureTestingModule({ imports: [PlainHostComponent] }).compileComponents();
    const fixture = TestBed.createComponent(PlainHostComponent);
    fixture.detectChanges();
    await fixture.whenStable();

    const el = fixture.nativeElement.querySelector('.error-message') as HTMLElement;
    expect(el.getAttribute('role')).toBe('alert');
    expect(el.classList.contains('error-message--warning')).toBe(true);
    expect(el.textContent).toContain('Could not load proposals');
    expect(el.textContent).toContain('Try again in a moment.');
  });

  it('derives title, message and tone from apiError (403 forbidden)', async () => {
    await TestBed.configureTestingModule({ imports: [ApiErrorHostComponent] }).compileComponents();
    const fixture = TestBed.createComponent(ApiErrorHostComponent);
    fixture.componentInstance.error = { kind: 'forbidden', status: 403, serverMessage: null, fieldErrors: [] };
    fixture.detectChanges();
    await fixture.whenStable();

    const el = fixture.nativeElement.querySelector('.error-message') as HTMLElement;
    expect(el.classList.contains('error-message--warning')).toBe(true);
    expect(el.textContent).toContain('Access denied');
    expect(el.querySelector('.error-message__retry')).toBeNull();
  });

  it('shows retry button for retryable errors (500 server-error)', async () => {
    await TestBed.configureTestingModule({ imports: [ApiErrorHostComponent] }).compileComponents();
    const fixture = TestBed.createComponent(ApiErrorHostComponent);
    fixture.componentInstance.error = { kind: 'server-error', status: 500, serverMessage: null, fieldErrors: [] };
    fixture.detectChanges();
    await fixture.whenStable();

    const retryBtn = fixture.nativeElement.querySelector('.error-message__retry') as HTMLElement | null;
    expect(retryBtn).not.toBeNull();
    expect(retryBtn?.textContent?.trim()).toBe('Try again');
  });

  it('emits retry output when Try again is clicked', async () => {
    await TestBed.configureTestingModule({ imports: [ApiErrorHostComponent] }).compileComponents();
    const fixture = TestBed.createComponent(ApiErrorHostComponent);
    fixture.componentInstance.error = { kind: 'network-error', status: 0, serverMessage: null, fieldErrors: [] };
    fixture.detectChanges();
    await fixture.whenStable();

    const retryBtn = fixture.nativeElement.querySelector('.error-message__retry') as HTMLButtonElement;
    retryBtn.click();
    expect(fixture.componentInstance.retried).toBe(true);
  });

  it('renders validation field errors for 422 responses', async () => {
    await TestBed.configureTestingModule({ imports: [ApiErrorHostComponent] }).compileComponents();
    const fixture = TestBed.createComponent(ApiErrorHostComponent);
    fixture.componentInstance.error = {
      kind: 'validation',
      status: 422,
      serverMessage: 'Validation failed',
      fieldErrors: [
        { field: 'title', message: 'must not be blank' },
        { field: 'beginDate', message: 'must be in the future' },
      ],
    };
    fixture.detectChanges();
    await fixture.whenStable();

    const el = fixture.nativeElement as HTMLElement;
    expect(el.textContent).toContain('title');
    expect(el.textContent).toContain('must not be blank');
    expect(el.textContent).toContain('beginDate');
  });
});
