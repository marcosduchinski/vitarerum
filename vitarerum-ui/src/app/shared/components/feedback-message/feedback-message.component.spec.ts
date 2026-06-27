import { ChangeDetectionStrategy, Component, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';

import { FeedbackMessageComponent, FeedbackMessageTone } from './feedback-message.component';

@Component({
  standalone: true,
  imports: [FeedbackMessageComponent],
  template: `
    <app-feedback-message
      title="Proposal forwarded"
      message="The proposal was sent to the selected reviewer."
      [tone]="tone()"
      [dismissible]="dismissible()"
      (dismissed)="dismissed.set(true)"
    />
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
class FeedbackHostComponent {
  readonly tone = signal<FeedbackMessageTone>('success');
  readonly dismissible = signal(false);
  readonly dismissed = signal(false);
}

describe('FeedbackMessageComponent', () => {
  it('renders success feedback as a polite status message', async () => {
    await TestBed.configureTestingModule({ imports: [FeedbackHostComponent] }).compileComponents();
    const fixture = TestBed.createComponent(FeedbackHostComponent);
    fixture.detectChanges();
    await fixture.whenStable();

    const message = fixture.nativeElement.querySelector('.feedback-message') as HTMLElement;

    expect(message.classList.contains('feedback-message--success')).toBe(true);
    expect(message.getAttribute('role')).toBe('status');
    expect(message.getAttribute('aria-live')).toBe('polite');
    expect(message.textContent).toContain('Proposal forwarded');
    expect(message.textContent).toContain('The proposal was sent to the selected reviewer.');
  });

  it('renders warning feedback as an assertive alert', async () => {
    await TestBed.configureTestingModule({ imports: [FeedbackHostComponent] }).compileComponents();
    const fixture = TestBed.createComponent(FeedbackHostComponent);
    fixture.componentInstance.tone.set('warning');
    fixture.detectChanges();
    await fixture.whenStable();

    const message = fixture.nativeElement.querySelector('.feedback-message') as HTMLElement;

    expect(message.classList.contains('feedback-message--warning')).toBe(true);
    expect(message.getAttribute('role')).toBe('alert');
    expect(message.getAttribute('aria-live')).toBe('assertive');
  });

  it('emits dismissed when the dismiss button is clicked', async () => {
    await TestBed.configureTestingModule({ imports: [FeedbackHostComponent] }).compileComponents();
    const fixture = TestBed.createComponent(FeedbackHostComponent);
    fixture.componentInstance.dismissible.set(true);
    fixture.detectChanges();
    await fixture.whenStable();

    const dismiss = fixture.nativeElement.querySelector(
      '.feedback-message__dismiss',
    ) as HTMLButtonElement;

    dismiss.click();

    expect(fixture.componentInstance.dismissed()).toBe(true);
  });
});
