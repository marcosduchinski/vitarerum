import { ChangeDetectionStrategy, Component, input } from '@angular/core';

export interface AgentExecutionMetadata {
  readonly label: string;
  readonly value: string;
}

/** Shared visual frame for one agent execution; workflow content is projected. */
@Component({
  selector: 'app-agent-execution-card',
  standalone: true,
  templateUrl: './agent-execution-card.component.html',
  styleUrl: './agent-execution-card.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AgentExecutionCardComponent {
  readonly title = input.required<string>();
  readonly status = input.required<string>();
  readonly metadata = input<readonly AgentExecutionMetadata[]>([]);

  protected statusLabel(): string {
    return this.status().replaceAll('_', ' ').toLowerCase();
  }
}
