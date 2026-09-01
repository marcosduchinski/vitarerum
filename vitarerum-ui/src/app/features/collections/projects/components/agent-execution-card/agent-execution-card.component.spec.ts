import { ComponentFixture, TestBed } from '@angular/core/testing';

import { AgentExecutionCardComponent } from './agent-execution-card.component';

describe('AgentExecutionCardComponent', () => {
  let fixture: ComponentFixture<AgentExecutionCardComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [AgentExecutionCardComponent],
    }).compileComponents();
    fixture = TestBed.createComponent(AgentExecutionCardComponent);
    fixture.componentRef.setInput('title', 'Reader assessment');
    fixture.componentRef.setInput('status', 'AWAITING_HUMAN_REVIEW');
    fixture.componentRef.setInput('metadata', [
      { label: 'Model', value: 'gemma4:12b' },
      { label: 'Latency', value: '420 ms' },
    ]);
    fixture.detectChanges();
  });

  it('renders the shared execution identity, status and metadata grammar', () => {
    const root = fixture.nativeElement as HTMLElement;

    expect(root.querySelector('h4')?.textContent).toContain('Reader assessment');
    expect(root.querySelector('.execution-card__status')?.textContent).toContain(
      'awaiting human review',
    );
    expect(root.querySelectorAll('.execution-card__meta div')).toHaveLength(2);
    expect(root.textContent).toContain('gemma4:12b');
    expect(root.textContent).toContain('420 ms');
  });
});
