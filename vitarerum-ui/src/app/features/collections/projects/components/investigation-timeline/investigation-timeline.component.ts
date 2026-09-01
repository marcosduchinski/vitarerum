import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

import {
  InvestigationIteration,
  ScientificReturnInvestigation,
} from '../../models/scientific-return.model';

/**
 * Origin of a piece of information on the timeline.
 *
 * The plan requires a reviewer to tell these apart at a glance: verified
 * evidence is a fact the deterministic rules established, a proposal is only
 * what the model asked for, and a policy decision is what the system allowed.
 * Presenting them alike would let a suggestion read as a finding.
 */
export type TrajectoryOrigin = 'verified' | 'proposal' | 'policy' | 'human';

interface TimelineStep {
  readonly key: string;
  readonly label: string;
  readonly origin: TrajectoryOrigin;
  readonly summary: string;
  readonly details: readonly string[];
}

const STOP_REASON_LABELS: Readonly<Record<string, string>> = {
  EVIDENCE_SUFFICIENT: 'Evidence found, ready for review',
  NO_RESULTS: 'No results',
  NO_EVIDENCE_ADDED: 'Results found, no new evidence',
  NO_PROGRESS: 'No progress',
  ACTION_REJECTED: 'Action refused by the policy',
  QUERY_REPEATED: 'Every variant had already been tried',
  BUDGET_EXHAUSTED: 'Budget exhausted',
  ITERATION_LIMIT_REACHED: 'Iteration limit reached',
  CANDIDATE_LIMIT_REACHED: 'Candidate ceiling reached',
  REASONER_UNAVAILABLE: 'Model unavailable',
  INVALID_PLAN: 'Model answered outside the schema',
  TOOL_UNAVAILABLE: 'Source unavailable',
  TOOL_FAILED: 'Tool failed',
  CANDIDATE_ALREADY_DECIDED: 'A human decided the candidate meanwhile',
  PRESENTED_FOR_REVIEW: 'Handed to review without searching',
  INSUFFICIENT_EVIDENCE: 'Model stopped for insufficient evidence',
};

export function stopReasonLabel(investigation: ScientificReturnInvestigation): string {
  const reason = investigation.stopReason;
  return reason ? (STOP_REASON_LABELS[reason] ?? reason) : 'Not finished';
}

export function budgetLabel(investigation: ScientificReturnInvestigation): string {
  const budget = investigation.budget;
  return `${budget.usedQueries}/${budget.maxQueries} queries · ${budget.createdCandidates}/${budget.maxNewCandidates} candidates`;
}

@Component({
  selector: 'app-investigation-timeline',
  standalone: true,
  templateUrl: './investigation-timeline.component.html',
  styleUrl: './investigation-timeline.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class InvestigationTimelineComponent {
  readonly investigation = input.required<ScientificReturnInvestigation>();

  readonly awaitingReview = computed(() => this.investigation().status === 'AWAITING_HUMAN_REVIEW');

  readonly failed = computed(() => this.investigation().status === 'FAILED');

  /** One flat, ordered list so the reader follows the cycle as it happened. */
  readonly steps = computed<readonly TimelineStep[]>(() =>
    this.investigation().iterations.flatMap((iteration) => this.stepsFor(iteration)),
  );

  private stepsFor(iteration: InvestigationIteration): readonly TimelineStep[] {
    const prefix = `it-${iteration.number}`;
    const steps: TimelineStep[] = [];

    const observation = iteration.observation;
    if (observation) {
      steps.push({
        key: `${prefix}-observation`,
        label: 'Observed',
        origin: 'verified',
        summary: `${observation.objects.length} consulted object(s), ${observation.triedQueries.length} query/queries already tried`,
        details: observation.triedQueries.map((query) => `Already tried: ${query}`),
      });
    }

    const plan = iteration.plan;
    if (plan) {
      steps.push({
        key: `${prefix}-plan`,
        label: 'Proposed by the model',
        origin: 'proposal',
        summary: `${plan.actionType}${plan.objectId ? ` on ${plan.objectId}` : ''}`,
        details: [plan.objective, plan.reasoningSummary].filter((item): item is string =>
          Boolean(item),
        ),
      });
    }

    const policy = iteration.policy;
    if (policy) {
      steps.push({
        key: `${prefix}-policy`,
        label: policy.authorized ? 'Authorised by the policy' : 'Refused by the policy',
        origin: 'policy',
        summary: policy.justification,
        details: policy.rejectionReason ? [`Reason: ${policy.rejectionReason}`] : [],
      });
    }

    const tool = iteration.tool;
    if (tool) {
      steps.push({
        key: `${prefix}-tool`,
        label: 'Executed',
        origin: 'policy',
        summary: `${tool.totalResults} result(s) from ${tool.sources.join(', ') || 'no source'}`,
        details: tool.executedQueries.map((query) => `Sent: ${query}`),
      });
    }

    const delta = iteration.evidenceDelta;
    if (delta) {
      steps.push({
        key: `${prefix}-delta`,
        label: 'Verified evidence',
        origin: 'verified',
        summary: delta.added.length
          ? `${delta.added.length} new: ${delta.added.join(', ')}`
          : 'No new verified evidence',
        details: [
          ...(delta.preserved.length ? [`Kept: ${delta.preserved.join(', ')}`] : []),
          ...(delta.removed.length ? [`Lost: ${delta.removed.join(', ')}`] : []),
        ],
      });
    }

    const reflection = iteration.reflection;
    if (reflection) {
      steps.push({
        key: `${prefix}-reflection`,
        label: 'Model reflection',
        origin: 'proposal',
        summary: reflection.evidenceDeltaSummary,
        details: [
          reflection.reasoningSummary,
          ...reflection.remainingGaps.map((gap) => `Gap: ${gap}`),
        ].filter((item): item is string => Boolean(item)),
      });
    }

    if (iteration.errorMessage) {
      steps.push({
        key: `${prefix}-error`,
        label: 'Failure',
        origin: 'policy',
        summary: iteration.errorMessage,
        details: [],
      });
    }
    return steps;
  }
}
