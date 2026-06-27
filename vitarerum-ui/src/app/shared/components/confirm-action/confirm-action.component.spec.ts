import { ChangeDetectionStrategy, Component, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';

import { ConfirmActionComponent } from './confirm-action.component';

@Component({
  standalone: true,
  imports: [ConfirmActionComponent],
  template: `
    <app-confirm-action
      title="Approve proposal"
      message="This will notify the researcher."
      confirmLabel="Approve"
      [disabled]="disabled()"
      (confirmed)="confirmCount.set(confirmCount() + 1)"
      (cancelled)="cancelCount.set(cancelCount() + 1)"
    />
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
class ConfirmActionHostComponent {
  readonly disabled = signal(false);
  readonly confirmCount = signal(0);
  readonly cancelCount = signal(0);
}

describe('ConfirmActionComponent', () => {
  it('emits confirm and cancel actions', async () => {
    await TestBed.configureTestingModule({
      imports: [ConfirmActionHostComponent],
    }).compileComponents();

    const fixture = TestBed.createComponent(ConfirmActionHostComponent);
    fixture.detectChanges();
    await fixture.whenStable();

    const buttons = fixture.nativeElement.querySelectorAll('button') as NodeListOf<HTMLButtonElement>;

    buttons[1]?.click();
    buttons[0]?.click();

    expect(fixture.componentInstance.confirmCount()).toBe(1);
    expect(fixture.componentInstance.cancelCount()).toBe(1);
  });

  it('does not emit confirm when disabled', async () => {
    await TestBed.configureTestingModule({
      imports: [ConfirmActionHostComponent],
    }).compileComponents();

    const fixture = TestBed.createComponent(ConfirmActionHostComponent);
    fixture.componentInstance.disabled.set(true);
    fixture.detectChanges();
    await fixture.whenStable();

    const confirmButton = fixture.nativeElement.querySelector(
      '.confirm-action__button--primary',
    ) as HTMLButtonElement | null;

    confirmButton?.click();

    expect(confirmButton?.disabled).toBe(true);
    expect(fixture.componentInstance.confirmCount()).toBe(0);
  });
});
