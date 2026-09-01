import { DatePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  input,
  resource,
  signal,
} from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { IDENTITY_SERVICE } from '@core/auth/identity.service';
import { ApiError, getApiErrorPresentation, toApiError } from '@core/http/api-error.model';
import { ConfirmModalComponent } from '@shared/components/confirm-modal/confirm-modal.component';
import { ErrorMessageComponent } from '@shared/components/error-message/error-message.component';
import { FeedbackMessageComponent } from '@shared/components/feedback-message/feedback-message.component';
import { LoadingStateComponent } from '@shared/components/loading-state/loading-state.component';
import { AgentFlowIconComponent } from '@shared/components/agent-flow-icon/agent-flow-icon.component';

import {
  AgentAnalysisFeedback,
  CandidateAnalysesModalComponent,
} from '../candidate-analyses-modal/candidate-analyses-modal.component';
import { CandidateInvestigationsModalComponent } from '../candidate-investigations-modal/candidate-investigations-modal.component';

import {
  CandidateAgentAnalysis,
  CandidateDecisionRecord,
  CandidateDecisionRequest,
  ScientificReturnCandidate,
  ScientificReturnCandidateStatus,
  ScientificReturnDecision,
  ScientificReturnInvestigation,
  FullAgenticInvestigation,
  AgenticTrajectoryEvent,
} from '../../models/scientific-return.model';
import { ScientificReturnApiService } from '../../services/scientific-return-api.service';

type DecisionDraft = Exclude<ScientificReturnDecision, 'CONFIRM'> | 'CONFIRM';
type TrajectoryFlow = 'in' | 'out' | 'none';

interface TrajectoryGroup {
  readonly key: string;
  readonly iteration: number | null;
  readonly events: readonly AgenticTrajectoryEvent[];
}

/**
 * Cut the flat trajectory at each replanning.
 *
 * Only the planning events carry an iteration number; the searches, the
 * readings and the endings that follow inherit the one in force, which is why
 * the number is carried forward instead of read per event. What comes before
 * the first plan — the curatorial memory — belongs to no iteration and leads
 * the list without a heading.
 */
function groupByIteration(events: readonly AgenticTrajectoryEvent[]): readonly TrajectoryGroup[] {
  const groups: { iteration: number | null; events: AgenticTrajectoryEvent[] }[] = [];
  let current: number | null = null;
  for (const event of events) {
    const iteration = event.payload['iteration'];
    if (typeof iteration === 'number') current = iteration;
    const last = groups.at(-1);
    if (last && last.iteration === current) {
      last.events.push(event);
    } else {
      groups.push({ iteration: current, events: [event] });
    }
  }
  return groups.map((group, index) => ({
    key: `${group.iteration ?? 'start'}-${index}`,
    iteration: group.iteration,
    events: group.events,
  }));
}
type CandidateFilter = ScientificReturnCandidateStatus | 'ALL';

function isNotFound(error: unknown): boolean {
  return error instanceof HttpErrorResponse && error.status === 404;
}

@Component({
  selector: 'app-scientific-return-panel',
  standalone: true,
  imports: [
    CandidateAnalysesModalComponent,
    CandidateInvestigationsModalComponent,
    ConfirmModalComponent,
    DatePipe,
    ErrorMessageComponent,
    FeedbackMessageComponent,
    AgentFlowIconComponent,
    LoadingStateComponent,
  ],
  templateUrl: './scientific-return-panel.component.html',
  styleUrl: './scientific-return-panel.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ScientificReturnPanelComponent {
  private readonly api = inject(ScientificReturnApiService);
  private readonly identity = inject(IDENTITY_SERVICE);

  readonly projectId = input.required<string>();
  protected readonly filterOptions: readonly CandidateFilter[] = [
    'PENDING',
    'CONFIRMED',
    'DISMISSED',
    'ALL',
  ];

  protected readonly watchResource = resource({
    params: () => this.projectId(),
    loader: async ({ params }) => {
      try {
        return await firstValueFrom(this.api.getWatch(params));
      } catch (error) {
        if (isNotFound(error)) return null;
        throw error;
      }
    },
  });
  protected readonly watch = computed(() => this.watchResource.value() ?? null);
  protected readonly filter = signal<CandidateFilter>('PENDING');
  protected readonly candidatesResource = resource({
    params: () => ({
      projectId: this.projectId(),
      watchId: this.watch()?.id ?? null,
      filter: this.filter(),
    }),
    loader: ({ params }) => {
      if (!params.watchId) {
        return Promise.resolve({ content: [], page: 0, size: 50, totalElements: 0, totalPages: 0 });
      }
      return firstValueFrom(
        this.api.listCandidates(params.projectId, params.filter === 'ALL' ? null : params.filter),
      );
    },
  });
  protected readonly runsResource = resource({
    params: () => this.watch()?.id ?? null,
    loader: ({ params }) => {
      if (!params) {
        return Promise.resolve({ content: [], page: 0, size: 10, totalElements: 0, totalPages: 0 });
      }
      return firstValueFrom(this.api.listRuns(params));
    },
  });
  protected readonly candidates = computed(() => this.candidatesResource.value()?.content ?? []);
  protected readonly runs = computed(() => this.runsResource.value()?.content ?? []);
  protected readonly fullAgenticResource = resource({
    params: () => this.watch()?.id ?? null,
    loader: ({ params }) =>
      params
        ? firstValueFrom(this.api.listFullAgenticInvestigations(params))
        : Promise.resolve([] as readonly FullAgenticInvestigation[]),
  });
  protected readonly fullAgenticInvestigations = computed(
    () => this.fullAgenticResource.value() ?? [],
  );
  protected readonly canReview = computed(() => {
    const group = this.identity.session()?.group;
    return group === 'CURATORIAL' || group === 'COLLECTIONS_MANAGEMENT' || group === 'DIRECTION';
  });
  protected readonly loading = computed(
    () => this.watchResource.isLoading() || this.candidatesResource.isLoading(),
  );
  protected readonly loadError = computed<ApiError | null>(() => {
    const error =
      this.watchResource.error() ??
      this.candidatesResource.error() ??
      this.runsResource.error() ??
      this.fullAgenticResource.error() ??
      null;
    return error ? toApiError(error) : null;
  });

  protected readonly busyAction = signal<string | null>(null);
  protected readonly closeConfirmOpen = signal(false);
  protected readonly intervalEditing = signal(false);
  protected readonly intervalDraft = signal('');
  protected readonly anchorEditing = signal(false);
  protected readonly anchorDraft = signal('');
  protected readonly actionError = signal<ApiError | null>(null);
  protected readonly feedback = signal<string | null>(null);
  protected readonly activeCandidateId = signal<string | null>(null);
  protected readonly decisionDraft = signal<DecisionDraft>('CONFIRM');
  protected readonly justification = signal('');
  protected readonly correctedTitle = signal('');
  protected readonly correctedDoi = signal('');
  protected readonly correctedUrl = signal('');
  protected readonly correctedAuthors = signal('');
  protected readonly expandedRunId = signal<string | null>(null);
  protected readonly decisionsByCandidate = signal<
    Readonly<Record<string, readonly CandidateDecisionRecord[]>>
  >({});
  protected readonly loadingHistoryId = signal<string | null>(null);
  protected readonly investigationsByCandidate = signal<
    Record<string, readonly ScientificReturnInvestigation[]>
  >({});
  protected readonly runningInvestigationId = signal<string | null>(null);
  protected readonly investigationsCandidateId = signal<string | null>(null);
  protected readonly loadingInvestigationsId = signal<string | null>(null);
  protected readonly investigationsError = signal<string | null>(null);
  protected readonly analysesByCandidate = signal<
    Readonly<Record<string, readonly CandidateAgentAnalysis[]>>
  >({});
  protected readonly loadingAgentAnalysisId = signal<string | null>(null);
  protected readonly feedbackBusyAnalysisId = signal<string | null>(null);
  protected readonly analysesCandidateId = signal<string | null>(null);
  protected readonly analysesError = signal<string | null>(null);

  /**
   * One modal instance serves the whole list, so the open candidate is looked
   * up here rather than rendered per row. Reading it back from `candidates()`
   * keeps the dialog on the refreshed record after a decision or a reload.
   */
  protected readonly investigationsCandidate = computed(() =>
    this.candidateById(this.investigationsCandidateId()),
  );
  protected readonly analysesCandidate = computed(() =>
    this.candidateById(this.analysesCandidateId()),
  );
  protected readonly openInvestigationsList = computed(() => {
    const id = this.investigationsCandidateId();
    return id ? (this.investigationsByCandidate()[id] ?? []) : [];
  });
  protected readonly openAnalysesList = computed(() => {
    const id = this.analysesCandidateId();
    return id ? (this.analysesByCandidate()[id] ?? []) : [];
  });
  protected readonly fullAgenticBusy = signal(false);
  protected readonly expandedFullAgenticId = signal<string | null>(null);
  protected readonly fullAgenticTrajectory = signal<
    Readonly<Partial<Record<string, readonly AgenticTrajectoryEvent[]>>>
  >({});
  protected readonly trajectoryGroups = computed(() => {
    const grouped: Record<string, readonly TrajectoryGroup[]> = {};
    for (const [investigationId, events] of Object.entries(this.fullAgenticTrajectory())) {
      grouped[investigationId] = groupByIteration(events ?? []);
    }
    return grouped;
  });

  protected setFilter(filter: CandidateFilter): void {
    this.filter.set(filter);
    this.closeDecision();
  }

  protected async activate(): Promise<void> {
    if (!this.canReview() || this.busyAction()) return;
    this.busyAction.set('activate');
    this.clearMessages();
    try {
      const watch = await firstValueFrom(this.api.activateWatch(this.projectId()));
      this.watchResource.set(watch);
      this.feedback.set('Scientific-return monitoring is active.');
    } catch (error) {
      this.actionError.set(toApiError(error));
    } finally {
      this.busyAction.set(null);
    }
  }

  protected startAnchorEdit(): void {
    const watch = this.watch();
    if (!watch || !this.canReview() || this.busyAction() || watch.status === 'CLOSED') return;
    // The input is a plain date, so it needs the YYYY-MM-DD prefix of the ISO value.
    this.anchorDraft.set(watch.scheduleAnchorAt.slice(0, 10));
    this.clearMessages();
    this.anchorEditing.set(true);
  }

  protected cancelAnchorEdit(): void {
    this.anchorEditing.set(false);
  }

  protected onAnchorInput(event: Event): void {
    this.anchorDraft.set((event.target as HTMLInputElement).value);
  }

  protected anchorInvalid(): boolean {
    return !this.anchorDraft() || Number.isNaN(Date.parse(this.anchorDraft()));
  }

  protected async saveAnchor(event: SubmitEvent): Promise<void> {
    event.preventDefault();
    const watch = this.watch();
    if (!watch || !this.canReview() || this.busyAction() || this.anchorInvalid()) return;
    this.busyAction.set('anchor');
    this.clearMessages();
    try {
      const updated = await firstValueFrom(
        this.api.updateWatch(watch.id, {
          scheduleAnchorAt: new Date(`${this.anchorDraft()}T00:00:00Z`).toISOString(),
        }),
      );
      this.watchResource.set(updated);
      this.anchorEditing.set(false);
      this.feedback.set('Reviews are now measured from the new start date.');
    } catch (error) {
      this.actionError.set(toApiError(error));
    } finally {
      this.busyAction.set(null);
    }
  }

  protected startIntervalEdit(): void {
    const watch = this.watch();
    if (!watch || !this.canReview() || this.busyAction() || watch.status === 'CLOSED') return;
    this.intervalDraft.set(String(watch.reviewIntervalDays));
    this.clearMessages();
    this.intervalEditing.set(true);
  }

  protected cancelIntervalEdit(): void {
    this.intervalEditing.set(false);
  }

  protected onIntervalInput(event: Event): void {
    this.intervalDraft.set((event.target as HTMLInputElement).value);
  }

  /** Mirrors the server range so the form refuses what the domain would reject. */
  protected intervalInvalid(): boolean {
    const days = Number(this.intervalDraft());
    return !Number.isInteger(days) || days < 1 || days > 365;
  }

  protected async saveInterval(event: SubmitEvent): Promise<void> {
    event.preventDefault();
    const watch = this.watch();
    if (!watch || !this.canReview() || this.busyAction() || this.intervalInvalid()) return;
    const days = Number(this.intervalDraft());
    if (days === watch.reviewIntervalDays) {
      this.intervalEditing.set(false);
      return;
    }
    this.busyAction.set('interval');
    this.clearMessages();
    try {
      const updated = await firstValueFrom(
        this.api.updateWatch(watch.id, { reviewIntervalDays: days }),
      );
      this.watchResource.set(updated);
      this.intervalEditing.set(false);
      this.feedback.set(
        `Review interval is now ${updated.reviewIntervalDays} days; the next review moved accordingly.`,
      );
    } catch (error) {
      this.actionError.set(toApiError(error));
    } finally {
      this.busyAction.set(null);
    }
  }

  protected openCloseConfirm(): void {
    if (!this.canReview() || this.busyAction()) return;
    this.closeConfirmOpen.set(true);
  }

  protected cancelCloseConfirm(): void {
    this.closeConfirmOpen.set(false);
  }

  /** Closing is terminal: a closed watch cannot be reopened, so it is confirmed first. */
  protected async confirmClose(): Promise<void> {
    await this.changeStatus('CLOSED');
    this.closeConfirmOpen.set(false);
  }

  protected async changeStatus(status: 'ACTIVE' | 'PAUSED' | 'CLOSED'): Promise<void> {
    const watch = this.watch();
    if (!watch || !this.canReview() || this.busyAction()) return;
    this.busyAction.set('status');
    this.clearMessages();
    try {
      this.watchResource.set(await firstValueFrom(this.api.changeWatchStatus(watch.id, status)));
      this.feedback.set(`Monitoring is now ${status.toLowerCase()}.`);
    } catch (error) {
      this.actionError.set(toApiError(error));
    } finally {
      this.busyAction.set(null);
    }
  }

  protected async runSearch(): Promise<void> {
    const watch = this.watch();
    if (!watch || watch.status !== 'ACTIVE' || !this.canReview() || this.busyAction()) return;
    this.busyAction.set('run');
    this.clearMessages();
    try {
      const run = await firstValueFrom(this.api.runWatch(watch.id));
      this.feedback.set(
        run.status === 'FAILED'
          ? 'The search was recorded, but the bibliographic source failed.'
          : run.newCandidateCount
            ? `Search completed with ${run.newCandidateCount} new candidate${run.newCandidateCount === 1 ? '' : 's'} for review.`
            : `Search completed with no new candidates (${run.candidateCount} previously known).`,
      );
      this.watchResource.reload();
      this.candidatesResource.reload();
      this.runsResource.reload();
    } catch (error) {
      this.actionError.set(toApiError(error));
    } finally {
      this.busyAction.set(null);
    }
  }

  protected openDecision(candidate: ScientificReturnCandidate, decision: DecisionDraft): void {
    this.activeCandidateId.set(candidate.id);
    this.decisionDraft.set(decision);
    this.justification.set('');
    this.correctedTitle.set(candidate.title);
    this.correctedDoi.set(candidate.doi ?? '');
    this.correctedUrl.set(candidate.url ?? '');
    this.correctedAuthors.set(candidate.authors.join(', '));
    this.clearMessages();
  }

  protected closeDecision(): void {
    this.activeCandidateId.set(null);
    this.justification.set('');
  }

  protected onTextInput(
    field: 'justification' | 'title' | 'doi' | 'url' | 'authors',
    event: Event,
  ): void {
    const value = (event.target as HTMLInputElement | HTMLTextAreaElement).value;
    const target = {
      justification: this.justification,
      title: this.correctedTitle,
      doi: this.correctedDoi,
      url: this.correctedUrl,
      authors: this.correctedAuthors,
    }[field];
    target.set(value);
  }

  protected decisionInvalid(): boolean {
    const decision = this.decisionDraft();
    if (decision === 'DISMISS') return !this.justification().trim();
    if (decision === 'CORRECT_AND_CONFIRM') return !this.correctedTitle().trim();
    return false;
  }

  protected async submitDecision(candidate: ScientificReturnCandidate): Promise<void> {
    if (
      candidate.id !== this.activeCandidateId() ||
      this.decisionInvalid() ||
      !this.canReview() ||
      this.busyAction()
    ) {
      return;
    }
    const decision = this.decisionDraft();
    const request: CandidateDecisionRequest = {
      decision,
      justification: this.justification().trim() || null,
      correction:
        decision === 'CORRECT_AND_CONFIRM'
          ? {
              title: this.correctedTitle().trim(),
              doi: this.correctedDoi().trim() || null,
              url: this.correctedUrl().trim() || null,
              authors: this.correctedAuthors()
                .split(',')
                .map((author) => author.trim())
                .filter(Boolean),
            }
          : null,
    };
    this.busyAction.set(candidate.id);
    this.clearMessages();
    try {
      await firstValueFrom(this.api.decideCandidate(candidate.id, request));
      if (request.justification) {
        try {
          await firstValueFrom(this.api.proposeKnowledge(candidate.id, request.justification));
          this.feedback.set(
            `${this.decisionFeedback(decision)} A reusable lesson was proposed for curator validation.`,
          );
        } catch {
          this.feedback.set(
            `${this.decisionFeedback(decision)} The decision was saved, but no reusable lesson could be proposed.`,
          );
        }
      } else {
        this.feedback.set(this.decisionFeedback(decision));
      }
      this.closeDecision();
      this.candidatesResource.reload();
    } catch (error) {
      this.actionError.set(toApiError(error));
    } finally {
      this.busyAction.set(null);
    }
  }

  protected toggleRun(runId: string): void {
    this.expandedRunId.update((current) => (current === runId ? null : runId));
  }

  protected sourceSearchUrl(source: string, query: string): string | null {
    const encodedQuery = encodeURIComponent(query);
    if (source === 'CROSSREF') {
      return `https://api.crossref.org/works?query=${encodedQuery}&rows=20`;
    }
    if (source === 'OPENALEX') {
      return `https://openalex.org/works?page=1&filter=${encodeURIComponent(`default.search:${query}`)}`;
    }
    if (source === 'EUROPE_PMC') {
      return `https://europepmc.org/search?query=${encodedQuery}`;
    }
    return null;
  }

  protected async toggleHistory(candidateId: string): Promise<void> {
    if (this.decisionsByCandidate()[candidateId]) {
      this.decisionsByCandidate.update((current) => {
        const next = { ...current };
        delete next[candidateId];
        return next;
      });
      return;
    }
    this.loadingHistoryId.set(candidateId);
    try {
      const decisions = await firstValueFrom(this.api.listDecisions(candidateId));
      this.decisionsByCandidate.update((current) => ({ ...current, [candidateId]: decisions }));
    } catch (error) {
      this.actionError.set(toApiError(error));
    } finally {
      this.loadingHistoryId.set(null);
    }
  }

  protected readonly expandedEventId = signal<string | null>(null);

  /**
   * A trajectory row said only its number, its kind and its date, while the
   * payload beside it carried the searches, the verdicts and the reasons. The
   * content was never missing — it was thrown away at the template.
   */
  private static readonly EVENT_TITLES: Readonly<Record<string, string>> = {
    MEMORY_RETRIEVED: 'Curatorial memory read',
    PLAN_CREATED: 'Plan',
    TOOL_STARTED: 'Search sent',
    TOOL_COMPLETED: 'Search answered',
    SEARCH_SKIPPED_DUPLICATE: 'Search skipped, already spent',
    COMPONENTS_COLLAPSED: 'Parts folded onto their publication',
    LLM_CALL_STARTED: 'Model call charged',
    LLM_CALL_COMPLETED: 'Model call returned',
    LLM_CALL_FAILED: 'Model call failed',
    LLM_CALL_TIMED_OUT: 'Model call timed out',
    ARTICLE_ASSESSED: 'Article read',
    CANDIDATE_LINKED: 'Candidate',
    PLANNER_ERROR: 'Planner contract rejected',
    PLANNER_FALLBACK: 'Planner given up on',
    SOURCE_WAIT_REJECTED: 'Source asked for too long a wait',
    COVERAGE_TRUNCATED: 'Project not covered in full',
    EXECUTION_SLICE_EXHAUSTED: 'Handed back to the queue',
    RECOVERY_LIMIT_EXHAUSTED: 'Given up after too many recoveries',
    ABANDONED: 'Closed as abandoned',
    ERROR: 'Error',
    STOPPED: 'Stopped',
  };

  protected eventTitle(event: AgenticTrajectoryEvent): string {
    return (
      ScientificReturnPanelComponent.EVENT_TITLES[event.kind] ??
      event.kind.replaceAll('_', ' ').toLowerCase()
    );
  }

  /**
   * Which side of the reasoning model a step sits on.
   *
   * The boundary is drawn around the model, not around the investigation, so
   * the column answers the question a curator actually has before deciding:
   * what was this model shown, and what did it claim from it.
   *
   * That leaves three kinds of step unmarked on purpose. `TOOL_STARTED` and
   * `CANDIDATE_LINKED` are the system executing a plan and persisting a
   * result, not the model speaking. The `LLM_CALL_*` pair carries no content
   * at all — only phase, duration and budget — so marking it would repeat the
   * direction of the `PLAN_CREATED` or `ARTICLE_ASSESSED` beside it. And a
   * failure, a skip or a lifecycle notice moved nothing either way.
   */
  private static readonly EVENT_FLOW: Readonly<Record<string, TrajectoryFlow>> = {
    // Curatorial knowledge injected into the planner prompt, and the source
    // records that become material for the next one.
    MEMORY_RETRIEVED: 'in',
    TOOL_COMPLETED: 'in',
    // The searches and the reasoning the model asked for, and its verdict on
    // an article it was shown: relevance, confidence, passages, contradictions.
    PLAN_CREATED: 'out',
    ARTICLE_ASSESSED: 'out',
  };

  protected eventFlow(event: AgenticTrajectoryEvent): TrajectoryFlow {
    return ScientificReturnPanelComponent.EVENT_FLOW[event.kind] ?? 'none';
  }

  protected eventFlowLabel(event: AgenticTrajectoryEvent): string {
    const flow = this.eventFlow(event);
    if (flow === 'in') return 'Given to the model';
    if (flow === 'out') return 'Produced by the model';
    return '';
  }

  /** The one line that makes a row worth reading without opening it. */
  protected eventSummary(event: AgenticTrajectoryEvent): string | null {
    const payload = event.payload;
    const text = (key: string): string => String(payload[key] ?? '');
    const seconds = (key: string): string => {
      const value = Number(payload[key] ?? 0);
      return value ? `${(value / 1000).toFixed(1)}s` : '';
    };
    const parts: (string | number | null)[] = [];
    switch (event.kind) {
      case 'MEMORY_RETRIEVED':
        return `${(payload['knowledgeItemIds'] as unknown[] | undefined)?.length ?? 0} items`;
      case 'PLAN_CREATED':
        parts.push(
          `${(payload['searches'] as unknown[] | undefined)?.length ?? 0} searches`,
          text('contractVersion'),
        );
        break;
      case 'TOOL_STARTED':
      case 'SEARCH_SKIPPED_DUPLICATE':
        parts.push(text('source'), text('strategy'), text('query'));
        break;
      case 'TOOL_COMPLETED':
        parts.push(text('source'), text('query'), `${text('resultCount')} results`);
        break;
      case 'COMPONENTS_COLLAPSED':
        return `${text('collapsedRecords')} records`;
      case 'LLM_CALL_STARTED':
        parts.push(text('phase'), `${text('llmCalls')} of ${text('maxLlmCalls')}`);
        break;
      case 'LLM_CALL_COMPLETED':
        parts.push(text('phase'), seconds('durationMs'));
        break;
      case 'LLM_CALL_FAILED':
      case 'LLM_CALL_TIMED_OUT':
        parts.push(text('phase'), seconds('durationMs'), text('message'));
        break;
      case 'ARTICLE_ASSESSED':
        // Source and query first, matching the search rows above: the records
        // of every source in the iteration are pooled before any of them is
        // read, so without them a verdict names no origin.
        parts.push(
          text('source'),
          text('query'),
          payload['relevant'] ? 'relevant' : 'not relevant',
          text('confidence'),
          text('inventoryEvidenceStatus'),
        );
        break;
      case 'CANDIDATE_LINKED':
        return text('relationKind').toLowerCase();
      case 'COVERAGE_TRUNCATED':
        return `${text('coveredObjects')} of ${text('consultedObjects')} objects`;
      case 'PLANNER_ERROR':
      case 'ERROR':
        return text('message') || null;
      case 'PLANNER_FALLBACK':
        return text('reason') || null;
      case 'SOURCE_WAIT_REJECTED':
        parts.push(text('source'), text('message'));
        break;
      case 'STOPPED':
        return text('status').toLowerCase();
      default:
        return null;
    }
    return parts.filter((part) => part !== null && part !== '').join(' · ') || null;
  }

  /** Everything the summary left out, shown only when the row is opened. */
  protected eventDetails(
    event: AgenticTrajectoryEvent,
  ): readonly { readonly label: string; readonly value: string }[] {
    return Object.entries(event.payload)
      .filter(([, value]) => value !== null && value !== undefined && value !== '')
      .map(([key, value]) => ({
        label: key.replaceAll(/([A-Z])/g, ' $1').toLowerCase(),
        value: typeof value === 'object' ? JSON.stringify(value, null, 1) : String(value),
      }));
  }

  protected toggleEvent(eventId: string): void {
    this.expandedEventId.set(this.expandedEventId() === eventId ? null : eventId);
  }

  /** The object an investigation covers, named rather than shown as a uuid. */
  protected objectLabel(investigation: FullAgenticInvestigation): string | null {
    const objectId = investigation.objectId;
    if (!objectId) return null;
    const consulted = this.watch()?.consultedObjects ?? [];
    const match = consulted.find((item) => item.id === objectId);
    return match ? `${match.inventoryNumber} · ${match.objectName}` : objectId;
  }

  /**
   * How much of the project has been investigated at all. Each consulted object
   * is investigated on its own, so a project is only covered once every object
   * has been reached — and a sweep may stop short of that.
   */
  protected readonly objectCoverage = computed(() => {
    const consulted = this.watch()?.consultedObjects ?? [];
    if (consulted.length < 2) return null;
    const reached = new Set(
      this.fullAgenticInvestigations()
        .map((investigation) => investigation.objectId)
        .filter((objectId): objectId is string => !!objectId),
    );
    return { reached: reached.size, total: consulted.length };
  });

  /** One recovery short of the ceiling, where the next stall ends the run. */
  protected isNearRecoveryLimit(investigation: FullAgenticInvestigation): boolean {
    const ceiling = investigation.maxRecoveries;
    // A ceiling of zero is a real setting — it makes the first recovery fatal —
    // so only an absent one means there is nothing to be near.
    if (ceiling === null || ceiling === undefined) return false;
    return (investigation.recoveryCount ?? 0) >= ceiling;
  }

  protected async startFullAgentic(watchId: string): Promise<void> {
    if (!this.canReview() || this.fullAgenticBusy()) return;
    this.fullAgenticBusy.set(true);
    this.clearMessages();
    try {
      await firstValueFrom(this.api.startFullAgenticInvestigation(watchId));
      this.fullAgenticResource.reload();
      this.feedback.set(
        'The autonomous investigation was queued. Its searches and reasoning will appear in the audit trail.',
      );
    } catch (error) {
      this.actionError.set(toApiError(error));
    } finally {
      this.fullAgenticBusy.set(false);
    }
  }

  protected async toggleFullAgentic(investigationId: string): Promise<void> {
    if (this.expandedFullAgenticId() === investigationId) {
      this.expandedFullAgenticId.set(null);
      return;
    }
    this.expandedFullAgenticId.set(investigationId);
    if (this.fullAgenticTrajectory()[investigationId]) return;
    try {
      const events = await firstValueFrom(this.api.getFullAgenticTrajectory(investigationId));
      this.fullAgenticTrajectory.update((current) => ({ ...current, [investigationId]: events }));
    } catch (error) {
      this.actionError.set(toApiError(error));
    }
  }

  protected async cancelFullAgentic(investigationId: string): Promise<void> {
    if (this.fullAgenticBusy()) return;
    this.fullAgenticBusy.set(true);
    try {
      await firstValueFrom(this.api.cancelFullAgenticInvestigation(investigationId));
      this.fullAgenticResource.reload();
      this.feedback.set('Cancellation was requested for the autonomous investigation.');
    } catch (error) {
      this.actionError.set(toApiError(error));
    } finally {
      this.fullAgenticBusy.set(false);
    }
  }

  /**
   * Enrichment is only meaningful while the candidate is undecided: the action
   * policy refuses a decided one, but only after the planner has already been
   * charged for a call, so the decision is taken here instead.
   */
  protected async investigateCandidate(candidate: ScientificReturnCandidate): Promise<void> {
    if (!this.canReview() || candidate.status !== 'PENDING' || this.runningInvestigationId()) {
      return;
    }
    const candidateId = candidate.id;
    this.runningInvestigationId.set(candidateId);
    this.clearMessages();
    try {
      const investigation = await firstValueFrom(this.api.startCandidateInvestigation(candidateId));
      this.investigationsByCandidate.update((current) => ({
        ...current,
        [candidateId]: [investigation, ...(current[candidateId] ?? [])],
      }));
      // The trajectory is the answer to what was just run, so it opens where
      // the reader is already looking instead of waiting behind a button.
      this.investigationsError.set(null);
      this.investigationsCandidateId.set(candidateId);
      // The candidate stays pending whatever the cycle found: only a human
      // decision records scientific return.
      this.feedback.set(
        investigation.status === 'AWAITING_HUMAN_REVIEW'
          ? 'The investigation found something reviewable. The candidate still needs your decision.'
          : `The investigation ended: ${investigation.stopReason ?? 'no reason recorded'}.`,
      );
      this.candidatesResource.reload();
    } catch (error) {
      this.actionError.set(toApiError(error));
    } finally {
      this.runningInvestigationId.set(null);
    }
  }

  protected async openInvestigations(candidate: ScientificReturnCandidate): Promise<void> {
    const candidateId = candidate.id;
    this.analysesCandidateId.set(null);
    this.investigationsCandidateId.set(candidateId);
    this.investigationsError.set(null);
    await this.loadInvestigations(candidateId);
  }

  protected closeInvestigations(): void {
    this.investigationsCandidateId.set(null);
  }

  private async loadInvestigations(candidateId: string): Promise<void> {
    this.loadingInvestigationsId.set(candidateId);
    try {
      const investigations = await firstValueFrom(
        this.api.listCandidateInvestigations(candidateId),
      );
      this.investigationsByCandidate.update((current) => ({
        ...current,
        [candidateId]: investigations,
      }));
    } catch (error) {
      // Reported inside the dialog: the panel-level banner would sit behind
      // the backdrop, where the reader who triggered the load cannot see it.
      this.investigationsError.set(getApiErrorPresentation(toApiError(error)).message);
    } finally {
      this.loadingInvestigationsId.set(null);
    }
  }

  protected async openReaderAnalysis(candidate: ScientificReturnCandidate): Promise<void> {
    const candidateId = candidate.id;
    this.investigationsCandidateId.set(null);
    this.analysesCandidateId.set(candidateId);
    this.analysesError.set(null);
    this.loadingAgentAnalysisId.set(candidateId);
    this.clearMessages();
    try {
      const analyses = await firstValueFrom(this.api.listAgentAnalyses(candidateId));
      this.analysesByCandidate.update((current) => ({
        ...current,
        [candidateId]: analyses,
      }));
    } catch (error) {
      this.analysesError.set(getApiErrorPresentation(toApiError(error)).message);
    } finally {
      this.loadingAgentAnalysisId.set(null);
    }
  }

  protected closeReaderAnalysis(): void {
    this.analysesCandidateId.set(null);
  }

  protected async recordAgentFeedback({ analysisId, value }: AgentAnalysisFeedback): Promise<void> {
    const candidateId = this.analysesCandidateId();
    if (!candidateId || !this.canReview() || this.feedbackBusyAnalysisId()) return;
    this.feedbackBusyAnalysisId.set(analysisId);
    this.clearMessages();
    try {
      const updated = await firstValueFrom(this.api.recordAgentAnalysisFeedback(analysisId, value));
      this.analysesByCandidate.update((current) => ({
        ...current,
        [candidateId]: (current[candidateId] ?? []).map((item) =>
          item.id === updated.id ? updated : item,
        ),
      }));
      this.feedback.set('Your assessment of the full-agentic reader was recorded.');
    } catch (error) {
      this.actionError.set(toApiError(error));
    } finally {
      this.feedbackBusyAnalysisId.set(null);
    }
  }

  protected candidateAuthors(candidate: ScientificReturnCandidate): string {
    return candidate.authors.join(', ') || 'Unknown authors';
  }

  protected evidenceLabel(type: string): string {
    return type.toLowerCase().replaceAll('_', ' ');
  }

  protected decisionLabel(decision: ScientificReturnDecision): string {
    return decision.toLowerCase().replaceAll('_', ' ');
  }

  private candidateById(candidateId: string | null): ScientificReturnCandidate | null {
    if (!candidateId) return null;
    return this.candidates().find((item) => item.id === candidateId) ?? null;
  }

  private clearMessages(): void {
    this.actionError.set(null);
    this.feedback.set(null);
  }

  private decisionFeedback(decision: ScientificReturnDecision): string {
    if (decision === 'CONFIRM' || decision === 'CORRECT_AND_CONFIRM') {
      return 'Candidate confirmed and added to the publication log.';
    }
    return 'Candidate dismissed.';
  }
}
