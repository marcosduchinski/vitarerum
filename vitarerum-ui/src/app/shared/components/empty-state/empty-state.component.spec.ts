import { ChangeDetectionStrategy, Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';

import { EmptyStateComponent } from './empty-state.component';

@Component({
  standalone: true,
  imports: [EmptyStateComponent],
  template: `
    <app-empty-state title="No proposals" message="Submitted proposals will appear here.">
      <button type="button">Refresh</button>
    </app-empty-state>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
class EmptyStateHostComponent {}

describe('EmptyStateComponent', () => {
  it('renders accessible empty state content and actions', async () => {
    await TestBed.configureTestingModule({
      imports: [EmptyStateHostComponent],
    }).compileComponents();

    const fixture = TestBed.createComponent(EmptyStateHostComponent);

    fixture.detectChanges();
    await fixture.whenStable();

    const section = fixture.nativeElement.querySelector('.empty-state') as HTMLElement | null;

    expect(section?.getAttribute('aria-live')).toBe('polite');
    expect(section?.textContent).toContain('No proposals');
    expect(section?.textContent).toContain('Submitted proposals will appear here.');
    expect(section?.querySelector('button')?.textContent).toContain('Refresh');
  });
});
