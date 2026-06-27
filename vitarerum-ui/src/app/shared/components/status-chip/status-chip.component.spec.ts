import { ChangeDetectionStrategy, Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';

import {
  getWorkflowStatusPresentation,
  StatusChipComponent,
  WorkflowStatus,
} from './status-chip.component';

@Component({
  standalone: true,
  imports: [StatusChipComponent],
  template: `<app-status-chip kind="proposal" [status]="status" />`,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
class StatusChipHostComponent {
  status: WorkflowStatus = 'PENDING';
}

describe('StatusChipComponent', () => {
  it('maps workflow statuses to labels and tones', () => {
    expect(getWorkflowStatusPresentation('SUBMITTED')).toEqual({
      label: 'Submitted',
      tone: 'submitted',
    });
    expect(getWorkflowStatusPresentation('IN_PROGRESS')).toEqual({
      label: 'In progress',
      tone: 'review',
    });
    expect(getWorkflowStatusPresentation('CREATED')).toEqual({
      label: 'Created',
      tone: 'submitted',
    });
  });

  it('renders an accessible status chip', async () => {
    await TestBed.configureTestingModule({
      imports: [StatusChipHostComponent],
    }).compileComponents();

    const fixture = TestBed.createComponent(StatusChipHostComponent);

    fixture.detectChanges();
    await fixture.whenStable();

    const chip = fixture.nativeElement.querySelector('.status-chip') as HTMLElement | null;

    expect(chip?.textContent?.trim()).toBe('Under review');
    expect(chip?.classList.contains('status-chip--review')).toBe(true);
    expect(chip?.getAttribute('aria-label')).toBe('Proposal status: Under review');
  });
});
