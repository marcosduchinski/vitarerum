import { ChangeDetectionStrategy, Component, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';

import { ConfirmModalComponent } from './confirm-modal.component';

@Component({
  standalone: true,
  imports: [ConfirmModalComponent],
  template: `
    <app-confirm-modal
      [open]="open()"
      title="Forward proposal"
      message="This will move the proposal to another reviewer."
      confirmLabel="Forward"
      cancelLabel="Keep editing"
      tone="warning"
      [pending]="pending()"
      (confirmed)="confirmCount.set(confirmCount() + 1)"
      (cancelled)="cancelCount.set(cancelCount() + 1)"
    />
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
class ConfirmModalHostComponent {
  readonly open = signal(true);
  readonly pending = signal(false);
  readonly confirmCount = signal(0);
  readonly cancelCount = signal(0);
}

describe('ConfirmModalComponent', () => {
  it('renders an accessible dialog with the selected tone', async () => {
    await TestBed.configureTestingModule({ imports: [ConfirmModalHostComponent] }).compileComponents();
    const fixture = TestBed.createComponent(ConfirmModalHostComponent);
    fixture.detectChanges();
    await fixture.whenStable();

    const dialog = fixture.nativeElement.querySelector('[role="dialog"]') as HTMLElement;

    expect(dialog).not.toBeNull();
    expect(dialog.getAttribute('aria-modal')).toBe('true');
    expect(dialog.classList.contains('confirm-modal__dialog--warning')).toBe(true);
    expect(dialog.textContent).toContain('Forward proposal');
    expect(dialog.textContent).toContain('This will move the proposal to another reviewer.');
  });

  it('emits confirm and cancel actions', async () => {
    await TestBed.configureTestingModule({ imports: [ConfirmModalHostComponent] }).compileComponents();
    const fixture = TestBed.createComponent(ConfirmModalHostComponent);
    fixture.detectChanges();
    await fixture.whenStable();

    const buttons = fixture.nativeElement.querySelectorAll(
      '.confirm-modal__button',
    ) as NodeListOf<HTMLButtonElement>;

    buttons[1]?.click();
    buttons[0]?.click();

    expect(fixture.componentInstance.confirmCount()).toBe(1);
    expect(fixture.componentInstance.cancelCount()).toBe(1);
  });

  it('does not emit while pending', async () => {
    await TestBed.configureTestingModule({ imports: [ConfirmModalHostComponent] }).compileComponents();
    const fixture = TestBed.createComponent(ConfirmModalHostComponent);
    fixture.componentInstance.pending.set(true);
    fixture.detectChanges();
    await fixture.whenStable();

    const buttons = fixture.nativeElement.querySelectorAll(
      '.confirm-modal__button',
    ) as NodeListOf<HTMLButtonElement>;

    buttons[1]?.click();
    buttons[0]?.click();

    expect(buttons[0]?.disabled).toBe(true);
    expect(buttons[1]?.disabled).toBe(true);
    expect(fixture.componentInstance.confirmCount()).toBe(0);
    expect(fixture.componentInstance.cancelCount()).toBe(0);
  });

  it('does not render when closed', async () => {
    await TestBed.configureTestingModule({ imports: [ConfirmModalHostComponent] }).compileComponents();
    const fixture = TestBed.createComponent(ConfirmModalHostComponent);
    fixture.componentInstance.open.set(false);
    fixture.detectChanges();
    await fixture.whenStable();

    expect(fixture.nativeElement.querySelector('[role="dialog"]')).toBeNull();
  });
});
