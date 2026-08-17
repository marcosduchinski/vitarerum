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
import { ApiError, toApiError } from '@core/http/api-error.model';
import { ErrorMessageComponent } from '@shared/components/error-message/error-message.component';
import { FeedbackMessageComponent } from '@shared/components/feedback-message/feedback-message.component';
import { LoadingStateComponent } from '@shared/components/loading-state/loading-state.component';

import { InvestigationTimelineComponent } from '../investigation-timeline/investigation-timeline.component';

import {
  CandidateAgentAnalysis,
  CandidateDecisionRecord,
  CandidateDecisionRequest,
  ScientificReturnCandidate,
  ScientificReturnCandidateStatus,
  ScientificReturnDecision,
  ScientificReturnAgentFeedback,
  ScientificReturnInvestigation,
} from '../../models/scientific-return.model';
import { ScientificReturnApiService } from '../../services/scientific-return-api.service';

type DecisionDraft = Exclude<ScientificReturnDecision, 'CONFIRM'> | 'CONFIRM';
type CandidateFilter = ScientificReturnCandidateStatus | 'ALL';

function isNotFound(error: unknown): boolean {
  return error instanceof HttpErrorResponse && error.status === 404;
}

@Component({
  selector: 'app-scientific-return-panel',
  standalone: true,
  imports: [
    DatePipe,
    ErrorMessageComponent,
    FeedbackMessageComponent,
    InvestigationTimelineComponent,
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
    'SNOOZED',
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
      null;
    return error ? toApiError(error) : null;
  });

  protected readonly busyAction = signal<string | null>(null);
  protected readonly actionError = signal<ApiError | null>(null);
  protected readonly feedback = signal<string | null>(null);
  protected readonly activeCandidateId = signal<string | null>(null);
  protected readonly decisionDraft = signal<DecisionDraft>('CONFIRM');
  protected readonly justification = signal('');
  protected readonly snoozedUntil = signal('');
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
  protected readonly watchInvestigations = signal<readonly ScientificReturnInvestigation[]>([]);

  protected readonly analysesByCandidate = signal<
    Readonly<Record<string, readonly CandidateAgentAnalysis[]>>
  >({});
  protected readonly loadingAgentAnalysisId = signal<string | null>(null);
  protected readonly feedbackBusyAnalysisId = signal<string | null>(null);

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
    this.snoozedUntil.set('');
    this.correctedTitle.set(candidate.title);
    this.correctedDoi.set(candidate.doi ?? '');
    this.correctedUrl.set(candidate.url ?? '');
    this.correctedAuthors.set(candidate.authors.join(', '));
    this.clearMessages();
  }

  protected closeDecision(): void {
    this.activeCandidateId.set(null);
    this.justification.set('');
    this.snoozedUntil.set('');
  }

  protected onTextInput(
    field: 'justification' | 'title' | 'doi' | 'url' | 'authors' | 'snoozedUntil',
    event: Event,
  ): void {
    const value = (event.target as HTMLInputElement | HTMLTextAreaElement).value;
    const target = {
      justification: this.justification,
      title: this.correctedTitle,
      doi: this.correctedDoi,
      url: this.correctedUrl,
      authors: this.correctedAuthors,
      snoozedUntil: this.snoozedUntil,
    }[field];
    target.set(value);
  }

  protected decisionInvalid(): boolean {
    const decision = this.decisionDraft();
    if (decision === 'DISMISS') return !this.justification().trim();
    if (decision === 'SNOOZE') return !this.snoozedUntil();
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
      snoozedUntil: decision === 'SNOOZE' ? new Date(this.snoozedUntil()).toISOString() : null,
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
      this.feedback.set(this.decisionFeedback(decision));
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

  protected async generateAgentAnalysis(candidateId: string): Promise<void> {
    if (!this.canReview() || this.loadingAgentAnalysisId()) return;
    this.loadingAgentAnalysisId.set(candidateId);
    this.clearMessages();
    try {
      const analysis = await firstValueFrom(this.api.generateAgentAnalysis(candidateId));
      this.analysesByCandidate.update((current) => ({
        ...current,
        [candidateId]: [analysis, ...(current[candidateId] ?? [])],
      }));
      this.feedback.set(
        analysis.status === 'COMPLETED'
          ? 'AI shadow analysis completed. No recommended action was executed.'
          : 'The AI analysis failed safely and was recorded in the audit trail.',
      );
    } catch (error) {
      this.actionError.set(toApiError(error));
    } finally {
      this.loadingAgentAnalysisId.set(null);
    }
  }

  protected async investigateWatch(watchId: string): Promise<void> {
    if (!this.canReview() || this.runningInvestigationId()) return;
    this.runningInvestigationId.set(watchId);
    this.clearMessages();
    try {
      const investigation = await firstValueFrom(this.api.startWatchInvestigation(watchId));
      this.watchInvestigations.update((current) => [investigation, ...current]);
      // Discovery may legitimately end without a candidate; that is a result,
      // not a failure, so the message says which happened.
      this.feedback.set(
        investigation.status === 'AWAITING_HUMAN_REVIEW'
          ? 'The investigation found a candidate. It still needs your decision.'
          : `The investigation ended without a candidate: ${investigation.stopReason ?? 'no reason recorded'}.`,
      );
      this.candidatesResource.reload();
    } catch (error) {
      this.actionError.set(toApiError(error));
    } finally {
      this.runningInvestigationId.set(null);
    }
  }

  protected async investigateCandidate(candidateId: string): Promise<void> {
    if (!this.canReview() || this.runningInvestigationId()) return;
    this.runningInvestigationId.set(candidateId);
    this.clearMessages();
    try {
      const investigation = await firstValueFrom(this.api.startCandidateInvestigation(candidateId));
      this.investigationsByCandidate.update((current) => ({
        ...current,
        [candidateId]: [investigation, ...(current[candidateId] ?? [])],
      }));
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

  protected async toggleInvestigations(candidateId: string): Promise<void> {
    if (this.investigationsByCandidate()[candidateId]) {
      this.investigationsByCandidate.update((current) => {
        const next = { ...current };
        delete next[candidateId];
        return next;
      });
      return;
    }
    try {
      const investigations = await firstValueFrom(
        this.api.listCandidateInvestigations(candidateId),
      );
      this.investigationsByCandidate.update((current) => ({
        ...current,
        [candidateId]: investigations,
      }));
    } catch (error) {
      this.actionError.set(toApiError(error));
    }
  }

  protected async toggleAgentHistory(candidateId: string): Promise<void> {
    if (this.analysesByCandidate()[candidateId]) {
      this.analysesByCandidate.update((current) => {
        const next = { ...current };
        delete next[candidateId];
        return next;
      });
      return;
    }
    this.loadingAgentAnalysisId.set(candidateId);
    this.clearMessages();
    try {
      const analyses = await firstValueFrom(this.api.listAgentAnalyses(candidateId));
      this.analysesByCandidate.update((current) => ({
        ...current,
        [candidateId]: analyses,
      }));
    } catch (error) {
      this.actionError.set(toApiError(error));
    } finally {
      this.loadingAgentAnalysisId.set(null);
    }
  }

  protected async recordAgentFeedback(
    candidateId: string,
    analysisId: string,
    value: ScientificReturnAgentFeedback,
  ): Promise<void> {
    if (!this.canReview() || this.feedbackBusyAnalysisId()) return;
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
      this.feedback.set('Your assessment of the AI recommendation was recorded.');
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

  protected agentActionLabel(action: string): string {
    return action.toLowerCase().replaceAll('_', ' ');
  }

  private clearMessages(): void {
    this.actionError.set(null);
    this.feedback.set(null);
  }

  private decisionFeedback(decision: ScientificReturnDecision): string {
    if (decision === 'CONFIRM' || decision === 'CORRECT_AND_CONFIRM') {
      return 'Candidate confirmed and added to the publication log.';
    }
    return decision === 'DISMISS' ? 'Candidate dismissed.' : 'Candidate snoozed.';
  }
}
