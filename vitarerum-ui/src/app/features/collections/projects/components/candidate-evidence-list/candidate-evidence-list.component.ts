import { ChangeDetectionStrategy, Component, input } from '@angular/core';

import { ScientificReturnEvidence } from '../../models/scientific-return.model';

/**
 * The verified matches behind a candidate, rendered the same way wherever a
 * candidate is shown.
 *
 * The review queue and the project panel each had their own list, their own
 * `evidenceLabel`, and — until recently — their own colour per strength, so
 * the same PRIMARY match was green on one screen and something else on the
 * other. One component is what keeps them from drifting apart again.
 */
@Component({
  selector: 'app-candidate-evidence-list',
  standalone: true,
  templateUrl: './candidate-evidence-list.component.html',
  styleUrl: './candidate-evidence-list.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CandidateEvidenceListComponent {
  readonly evidences = input.required<readonly ScientificReturnEvidence[]>();

  /** Which source field carried the match. The queue triages across projects
   * and needs it; inside a project the reader already has the context. */
  readonly showProvenance = input(false);

  protected typeLabel(evidence: ScientificReturnEvidence): string {
    return evidence.type.toLowerCase().replaceAll('_', ' ');
  }

  protected sourceLabel(sourceField: string): string {
    const label = sourceField.replaceAll('_', ' ').replaceAll('+', ' + ');
    return label.charAt(0).toUpperCase() + label.slice(1);
  }
}
