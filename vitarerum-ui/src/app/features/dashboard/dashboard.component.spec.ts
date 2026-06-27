import { TestBed } from '@angular/core/testing';

import { DashboardComponent } from './dashboard.component';

describe('DashboardComponent', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [DashboardComponent],
    }).compileComponents();
  });

  it('renders signal-derived dashboard totals and metrics', async () => {
    const fixture = TestBed.createComponent(DashboardComponent);

    fixture.detectChanges();
    await fixture.whenStable();

    const compiled = fixture.nativeElement as HTMLElement;
    const metricCards = compiled.querySelectorAll('.metric');

    expect(compiled.textContent).toContain('24 open items');
    expect(metricCards).toHaveLength(3);
    expect(metricCards[0]?.textContent).toContain('New proposals');
    expect(metricCards[0]?.textContent).toContain('12');
  });
});
