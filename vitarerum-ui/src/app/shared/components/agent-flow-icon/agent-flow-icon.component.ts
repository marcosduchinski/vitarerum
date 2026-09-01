import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

export type AgentFlowDirection = 'in' | 'out';

/**
 * A robot paired with a comic cue, drawn because PrimeIcons has neither shape.
 *
 * Out is the robot with an empty speech balloon whose tail points back at it:
 * the agent said this. In is the robot with sound waves breaking against it:
 * something reached the agent from outside. The robot swaps sides with its
 * cue, so the pair reads as a direction before the colour is even noticed.
 */
@Component({
  selector: 'app-agent-flow-icon',
  standalone: true,
  templateUrl: './agent-flow-icon.component.html',
  styleUrl: './agent-flow-icon.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AgentFlowIconComponent {
  readonly flow = input.required<AgentFlowDirection>();

  /** Speaking robot on the left, listening robot on the right. */
  protected readonly robotShift = computed(() => (this.flow() === 'out' ? 0 : 17));
}
