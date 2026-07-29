import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  computed,
  inject,
  input,
  linkedSignal,
  resource,
  signal,
  viewChild,
} from '@angular/core';
import { DOCUMENT } from '@angular/common';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';
import { firstValueFrom, Observable } from 'rxjs';

import { ApiError, toApiError } from '@core/http/api-error.model';
import { EmptyStateComponent } from '@shared/components/empty-state/empty-state.component';
import { ErrorMessageComponent } from '@shared/components/error-message/error-message.component';
import { LoadingStateComponent } from '@shared/components/loading-state/loading-state.component';
import { PaginationComponent } from '@shared/components/pagination/pagination.component';
import { highlightToSafeMarkup } from '@shared/utils/highlight-html.util';

import {
  MentionedObject,
  MuseumQuestionTriage,
  ObjectTriageHit,
  ObjectTriageMatch,
  SearchTermDraft,
  TriageVerdict,
  UseCategoryClassification,
  UseCategoryClassificationAudit,
  UseCategoryClassificationOutcome,
  UseCategoryClassifierKind,
  UseCategoryOperationalClassifier,
  UseCategoryScore,
  UseCategoryScoreSource,
  UseCategoryValue,
} from '../../models/museum-question-triage.model';
import {
  MuseumQuestion,
  MuseumQuestionPage,
  MuseumQuestionStatus,
} from '../../models/museum-question.model';
import { MUSEUM_QUESTION_MANAGEMENT_SERVICE } from '../../services/museum-question-management.service';

type QuestionDetailPanel = 'message' | 'history' | 'ai-assistance';
type ReplyEditorCommand = 'bold' | 'italic' | 'insertUnorderedList' | 'removeFormat';
type SearchTermField = 'english' | 'portuguese';

interface TriageHitRow {
  readonly key: string;
  readonly english: string;
  readonly portuguese: string;
  readonly hit: ObjectTriageHit;
}

interface TriageObjectResult extends MentionedObject {
  readonly key: string;
  readonly languagesSearched: readonly string[];
  /** Full merged/deduplicated list — used for the match count and for
   * "Add to reply" selection, which must work across every page. */
  readonly hits: readonly TriageHitRow[];
  /** Just the current page's slice of `hits`, for rendering. */
  readonly pagedHits: readonly TriageHitRow[];
  readonly page: number;
  readonly totalPages: number;
}

// A staff-submitted search term cannot exceed this length per field
// (backend rejects with 422 above it — kept in sync with
// _MAX_TERM_FIELD_LENGTH in app/ai/museum_question_triage/application/use_cases.py).
const MAX_SEARCH_TERM_FIELD_LENGTH = 200;
const MAX_STAFF_SEARCH_TERMS = 10;

// Backend no longer caps matches (see SEARCH_FETCH_LIMIT_PER_LANGUAGE) — the
// full list is paginated here instead, at a size that still fits the panel.
const TRIAGE_HITS_PAGE_SIZE = 5;
const ELEMENT_NODE = 1;
const TEXT_NODE = 3;
const ALLOWED_RICH_TEXT_TAGS = new Set(['B', 'BR', 'EM', 'I', 'LI', 'OL', 'P', 'STRONG', 'UL']);
const BLOCKED_RICH_TEXT_TAGS = new Set([
  'EMBED',
  'IFRAME',
  'LINK',
  'META',
  'OBJECT',
  'SCRIPT',
  'STYLE',
]);

const STATUS_LABELS: Record<MuseumQuestionStatus, string> = {
  SUBMITTED: 'Submitted',
  ANSWERED: 'Answered',
  OUT_OF_SCOPE: 'Out of scope',
  CLOSED: 'Closed',
};

const USE_CATEGORY_LABELS: Record<string, string> = {
  EXHIBITION: 'Exhibition',
  PUBLISHING_IMAGES: 'Publishing images',
  LEARNING_EVENTS: 'Learning events',
  ANSWERING_ENQUIRIES: 'Answering enquiries',
  RESEARCH_PROJECTS: 'Research projects',
  OPERATING_MACHINERY: 'Operating machinery',
  PLAYING_INSTRUMENTS: 'Playing instruments',
  FILMING: 'Filming',
  INSPIRING_NEW_WORK: 'Inspiring new work',
};

const USE_CATEGORY_OPTIONS: readonly UseCategoryValue[] = [
  'EXHIBITION',
  'PUBLISHING_IMAGES',
  'LEARNING_EVENTS',
  'ANSWERING_ENQUIRIES',
  'RESEARCH_PROJECTS',
  'OPERATING_MACHINERY',
  'PLAYING_INSTRUMENTS',
  'FILMING',
  'INSPIRING_NEW_WORK',
];

const CLASSIFIER_KIND_LABELS: Record<UseCategoryClassifierKind, string> = {
  LLM: 'LLM',
  EMBEDDING: 'Embedding',
  CASCADE: 'Cascade',
};

const OPERATIONAL_CLASSIFIER_LABELS: Record<UseCategoryOperationalClassifier, string> = {
  LLM: 'Operational: LLM',
  CASCADE_SEED: 'Operational: Cascade seed',
  CASCADE_CALIBRATED: 'Operational: Cascade calibrated',
};

const USE_CATEGORY_SEARCH_POLICY_LABELS: Record<string, string> = {
  EXHIBITION: 'No catalogue search',
  PUBLISHING_IMAGES: 'Search if object named',
  LEARNING_EVENTS: 'No catalogue search',
  ANSWERING_ENQUIRIES: 'Search if object named',
  RESEARCH_PROJECTS: 'Catalogue search',
  OPERATING_MACHINERY: 'Search if object named',
  PLAYING_INSTRUMENTS: 'Search if object named',
  FILMING: 'No catalogue search',
  INSPIRING_NEW_WORK: 'Search if object named',
};

const SCORE_SOURCE_LABELS: Record<UseCategoryScoreSource, string> = {
  LLM: 'LLM',
  EMBEDDING: 'Embedding',
};

@Component({
  selector: 'app-museum-question-detail-page',
  standalone: true,
  imports: [
    RouterLink,
    LoadingStateComponent,
    ErrorMessageComponent,
    EmptyStateComponent,
    PaginationComponent,
  ],
  templateUrl: './museum-question-detail-page.component.html',
  styleUrl: './museum-question-detail-page.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class MuseumQuestionDetailPageComponent {
  private readonly document = inject(DOCUMENT);
  private readonly service = inject(MUSEUM_QUESTION_MANAGEMENT_SERVICE);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);
  private readonly sanitizer = inject(DomSanitizer);
  private readonly replyEditor = viewChild<ElementRef<HTMLElement>>('replyEditor');

  readonly id = input.required<string>();
  readonly tab = input<string>();

  protected readonly activePanel = linkedSignal<QuestionDetailPanel>(() =>
    this.normalizeTab(this.tab()),
  );
  protected readonly detailRefreshToken = signal(0);
  protected readonly answerBody = signal('');
  protected readonly outOfScopeReason = signal('');
  protected readonly confirmOutOfScope = signal(false);
  protected readonly confirmClose = signal(false);
  protected readonly busy = signal(false);
  protected readonly actionError = signal<ApiError | null>(null);
  protected readonly triageRefreshToken = signal(0);
  protected readonly triageBusy = signal(false);
  protected readonly triageError = signal<ApiError | null>(null);
  protected readonly selectedTriageHitKeys = signal<ReadonlySet<string>>(new Set());
  protected readonly selectedTriageHit = signal<TriageHitRow | null>(null);
  protected readonly triageHitPages = signal<ReadonlyMap<string, number>>(new Map());
  protected readonly TRIAGE_HITS_PAGE_SIZE = TRIAGE_HITS_PAGE_SIZE;
  protected readonly MAX_SEARCH_TERM_FIELD_LENGTH = MAX_SEARCH_TERM_FIELD_LENGTH;
  protected readonly MAX_STAFF_SEARCH_TERMS = MAX_STAFF_SEARCH_TERMS;
  protected readonly verdictOverridePending = signal(false);
  protected readonly verdictOverrideBusy = signal(false);
  protected readonly searchTermsBusy = signal(false);
  protected readonly searchTermsError = signal<ApiError | null>(null);
  protected readonly useCategoriesBusy = signal(false);
  protected readonly useCategoriesError = signal<ApiError | null>(null);
  protected readonly useCategoryOptions = USE_CATEGORY_OPTIONS;

  protected readonly questionResource = resource({
    params: () => ({ id: this.id(), refresh: this.detailRefreshToken() }),
    loader: ({ params }) => firstValueFrom(this.service.get(params.id)),
  });

  protected readonly question = computed(() => this.questionResource.value() ?? null);
  protected readonly questionError = computed<ApiError | null>(() => {
    const err = this.questionResource.error();
    return err ? toApiError(err) : null;
  });

  protected readonly historyResource = resource<
    MuseumQuestionPage | null,
    {
      readonly currentQuestionId: string | null;
      readonly requesterEmail: string | null;
      readonly createdAt: string | null;
      readonly refresh: number;
    }
  >({
    params: () => {
      const question = this.question();
      return {
        currentQuestionId: question?.id ?? null,
        requesterEmail: question?.requesterEmail ?? null,
        createdAt: question?.createdAt ?? null,
        refresh: this.detailRefreshToken(),
      };
    },
    loader: ({ params }) => {
      if (!params.requesterEmail) return Promise.resolve(null);
      return firstValueFrom(
        this.service.list({
          requesterEmail: params.requesterEmail,
          page: 0,
          size: 100,
        }),
      );
    },
  });

  protected readonly historyError = computed<ApiError | null>(() => {
    const err = this.historyResource.error();
    return err ? toApiError(err) : null;
  });
  protected readonly previousQuestions = computed<readonly MuseumQuestion[]>(() => {
    const question = this.question();
    const page = this.historyResource.value();
    if (!question || !page) return [];
    return page.content
      .filter((item) => item.id !== question.id && item.createdAt < question.createdAt)
      .sort((a, b) => b.createdAt.localeCompare(a.createdAt));
  });
  protected readonly previousQuestionsTotal = computed(() => {
    const question = this.question();
    const page = this.historyResource.value();
    if (!question || !page) return 0;
    return Math.max(0, page.totalElements - 1);
  });

  protected readonly triageResource = resource({
    params: () => ({ id: this.id(), refresh: this.triageRefreshToken() }),
    loader: ({ params }) => firstValueFrom(this.service.getTriage(params.id)),
  });

  protected readonly classificationAuditResource = resource({
    params: () => ({ id: this.id(), refresh: this.triageRefreshToken() }),
    loader: ({ params }) => firstValueFrom(this.service.listTriageClassifications(params.id)),
  });

  protected readonly triage = computed<MuseumQuestionTriage | null>(
    () => this.triageResource.value() ?? null,
  );
  protected readonly triageResourceError = computed<ApiError | null>(() => {
    const err = this.triageResource.error();
    return err ? toApiError(err) : null;
  });
  /** The verdict that actually applies — a staff override if one was made,
   * otherwise the AI's own verdict. All display logic reads this, never
   * `triage().verdict` directly (that field is the AI's untouched original,
   * kept only for reference). */
  protected readonly effectiveVerdict = computed<TriageVerdict | null>(
    () => this.triage()?.effectiveVerdict ?? null,
  );
  protected readonly useCategoryClassification = computed<UseCategoryClassification | null>(
    () => this.triage()?.useCategoryClassification ?? null,
  );
  protected readonly useCategoryOperationalClassifier = computed<UseCategoryOperationalClassifier>(
    () => this.triage()?.useCategoryOperationalClassifier ?? 'LLM',
  );
  protected readonly useCategoryClassifierRuns = computed<
    readonly UseCategoryClassificationAudit[]
  >(() => this.classificationAuditResource.value()?.classifications ?? []);
  protected readonly displayedUseCategoryClassification = computed<
    UseCategoryClassification | UseCategoryClassificationAudit | null
  >(() => this.useCategoryClassification());
  protected readonly assignedUseCategories = computed<readonly UseCategoryScore[]>(
    () => this.displayedUseCategoryClassification()?.assignedCategories ?? [],
  );
  protected readonly categoryDraft = linkedSignal<ReadonlySet<UseCategoryValue>>(
    () => new Set(this.assignedUseCategories().map((score) => score.category)),
  );
  protected readonly categoryDraftOutcome = linkedSignal<UseCategoryClassificationOutcome>(
    () => this.displayedUseCategoryClassification()?.outcome ?? 'CATEGORIZED',
  );
  protected readonly categoryDraftChanged = computed(() => {
    const current = new Set(this.assignedUseCategories().map((score) => score.category));
    const draft = this.categoryDraft();
    const currentOutcome = this.displayedUseCategoryClassification()?.outcome ?? 'CATEGORIZED';
    if (currentOutcome !== this.categoryDraftOutcome()) return true;
    if (current.size !== draft.size) return true;
    return [...draft].some((category) => !current.has(category));
  });
  protected readonly canSubmitUseCategoryDraft = computed(() => {
    if (!this.categoryDraftChanged() || this.useCategoriesBusy()) return false;
    if (this.triageResource.isLoading()) return false;
    return this.categoryDraftOutcome() === 'UNCLEAR' || this.categoryDraft().size > 0;
  });
  protected readonly triageObjectResults = computed<readonly TriageObjectResult[]>(() => {
    const pages = this.triageHitPages();
    const triage = this.triage();
    const originByKey = new Map(
      (triage?.mentionedObjects ?? []).map((obj) => [this.triageObjectKey(obj), obj.origin]),
    );
    return (triage?.objectMatches ?? []).map((match) => {
      const key = this.triageObjectKey(match);
      const hits = match.hits.map((hit) => this.triageHitRow(match, hit));
      const totalPages = Math.max(1, Math.ceil(hits.length / TRIAGE_HITS_PAGE_SIZE));
      const page = Math.min(pages.get(key) ?? 0, totalPages - 1);
      return {
        key,
        english: match.english,
        portuguese: match.portuguese,
        origin: originByKey.get(key) ?? 'AI',
        languagesSearched: match.languagesSearched,
        hits,
        page,
        totalPages,
        pagedHits: hits.slice(page * TRIAGE_HITS_PAGE_SIZE, (page + 1) * TRIAGE_HITS_PAGE_SIZE),
      };
    });
  });
  /** Editable working copy of the search terms — resets whenever the triage
   * reloads (e.g. after a successful submit, or a re-run). Deliberately typed
   * as `SearchTermDraft` (no `origin`): the backend computes provenance from
   * the diff, this is just what the staff is editing right now. */
  protected readonly termsDraft = linkedSignal<readonly SearchTermDraft[]>(() =>
    (this.triage()?.mentionedObjects ?? []).map(({ english, portuguese }) => ({
      english,
      portuguese,
    })),
  );
  protected readonly canAddSearchTerm = computed(
    () => this.termsDraft().length < MAX_STAFF_SEARCH_TERMS && !this.searchTermsBusy(),
  );
  protected readonly selectedTriageHitRows = computed<readonly TriageHitRow[]>(() => {
    const selectedKeys = this.selectedTriageHitKeys();
    return this.triageObjectResults()
      .flatMap((item) => item.hits)
      .filter((row) => selectedKeys.has(row.key));
  });

  protected selectPanel(panel: QuestionDetailPanel): void {
    this.activePanel.set(panel);
    this.syncUrl({ tab: panel });
  }

  protected onTextInput(field: 'reason', event: Event): void {
    const value = (event.target as HTMLTextAreaElement).value;
    if (field === 'reason') this.outOfScopeReason.set(value);
  }

  protected onAnswerInput(event: Event): void {
    const editor = event.target as HTMLElement;
    this.answerBody.set(this.sanitizeRichTextHtml(editor.innerHTML));
  }

  protected applyEditorCommand(command: 'bold' | 'italic' | 'insertUnorderedList'): void {
    this.executeEditorCommand(command);
  }

  protected clearReplyFormatting(): void {
    this.executeEditorCommand('removeFormat');
  }

  protected canSendAnswer(): boolean {
    return this.hasAnswerContent() && !this.busy();
  }

  protected async answer(question: MuseumQuestion): Promise<void> {
    const answerBody = this.currentSanitizedAnswerBody();
    if (!answerBody) return;
    await this.run(() => this.service.answer(question.id, { answerBody }));
    const editor = this.replyEditor()?.nativeElement;
    if (editor) editor.innerHTML = '';
    this.answerBody.set('');
  }

  protected async markOutOfScope(question: MuseumQuestion): Promise<void> {
    if (!this.confirmOutOfScope()) {
      this.confirmOutOfScope.set(true);
      this.confirmClose.set(false);
      return;
    }
    await this.run(() =>
      this.service.markOutOfScope(question.id, {
        reason: this.outOfScopeReason().trim() || null,
      }),
    );
    this.outOfScopeReason.set('');
    this.confirmOutOfScope.set(false);
  }

  protected async close(question: MuseumQuestion): Promise<void> {
    if (!this.confirmClose()) {
      this.confirmClose.set(true);
      this.confirmOutOfScope.set(false);
      return;
    }
    await this.run(() => this.service.close(question.id));
    this.confirmClose.set(false);
  }

  protected async triggerTriage(question: MuseumQuestion): Promise<void> {
    if (this.triageBusy()) return;
    this.triageBusy.set(true);
    this.triageError.set(null);
    this.selectPanel('ai-assistance');
    try {
      await firstValueFrom(this.service.runTriage(question.id));
      this.selectedTriageHitKeys.set(new Set());
      this.selectedTriageHit.set(null);
      this.triageHitPages.set(new Map());
      this.triageRefreshToken.update((value) => value + 1);
    } catch (err) {
      this.triageError.set(toApiError(err));
    } finally {
      this.triageBusy.set(false);
    }
  }

  protected refreshTriage(): void {
    this.triageRefreshToken.update((value) => value + 1);
  }

  protected cancelConfirmations(): void {
    this.confirmOutOfScope.set(false);
    this.confirmClose.set(false);
  }

  /** Label depends on the *current* effective verdict so the action is
   * never ambiguous — never a generic "contest classification". */
  protected verdictActionLabel(): string {
    return this.effectiveVerdict() === 'OUT_OF_SCOPE'
      ? 'Marcar como dentro de escopo'
      : 'Marcar como fora de escopo';
  }

  protected verdictConfirmLabel(): string {
    return this.effectiveVerdict() === 'OUT_OF_SCOPE'
      ? 'Confirm mark in scope'
      : 'Confirm mark out of scope';
  }

  protected async contestVerdict(): Promise<void> {
    if (!this.verdictOverridePending()) {
      this.verdictOverridePending.set(true);
      return;
    }
    const triage = this.triage();
    if (!triage) return;
    const nextVerdict: TriageVerdict =
      triage.effectiveVerdict === 'OUT_OF_SCOPE' ? 'IN_SCOPE' : 'OUT_OF_SCOPE';

    this.verdictOverrideBusy.set(true);
    this.triageError.set(null);
    try {
      await firstValueFrom(this.service.overrideTriageVerdict(triage.questionId, nextVerdict));
      this.triageRefreshToken.update((value) => value + 1);
      this.verdictOverridePending.set(false);
    } catch (err) {
      this.triageError.set(toApiError(err));
    } finally {
      this.verdictOverrideBusy.set(false);
    }
  }

  protected cancelVerdictOverride(): void {
    this.verdictOverridePending.set(false);
  }

  protected onSearchTermInput(index: number, field: SearchTermField, event: Event): void {
    const value = (event.target as HTMLInputElement).value;
    this.termsDraft.update((current) =>
      current.map((term, i) => (i === index ? { ...term, [field]: value } : term)),
    );
  }

  protected addSearchTermDraft(): void {
    this.termsDraft.update((current) => [...current, { english: '', portuguese: '' }]);
  }

  protected removeSearchTermDraft(index: number): void {
    this.termsDraft.update((current) => current.filter((_, i) => i !== index));
  }

  protected async submitSearchTerms(): Promise<void> {
    const triage = this.triage();
    if (!triage || this.searchTermsBusy()) return;

    this.searchTermsBusy.set(true);
    this.searchTermsError.set(null);
    try {
      await firstValueFrom(
        this.service.syncTriageSearchTerms(triage.questionId, this.termsDraft()),
      );
      this.selectedTriageHitKeys.set(new Set());
      this.triageHitPages.set(new Map());
      this.triageRefreshToken.update((value) => value + 1);
    } catch (err) {
      this.searchTermsError.set(toApiError(err));
    } finally {
      this.searchTermsBusy.set(false);
    }
  }

  protected isCategoryDraftSelected(category: UseCategoryValue): boolean {
    return this.categoryDraft().has(category);
  }

  protected onCategoryDraftToggle(category: UseCategoryValue, event: Event): void {
    const checked = (event.target as HTMLInputElement).checked;
    this.categoryDraft.update((current) => {
      const next = new Set(current);
      if (checked) next.add(category);
      else next.delete(category);
      return next;
    });
    if (checked) this.categoryDraftOutcome.set('CATEGORIZED');
  }

  protected onUseCategoryUnclearToggle(event: Event): void {
    const checked = (event.target as HTMLInputElement).checked;
    if (checked) {
      this.categoryDraft.set(new Set());
      this.categoryDraftOutcome.set('UNCLEAR');
    } else {
      this.categoryDraftOutcome.set('CATEGORIZED');
    }
  }

  protected async submitUseCategories(): Promise<void> {
    const triage = this.triage();
    if (!triage || this.useCategoriesBusy()) return;
    this.useCategoriesBusy.set(true);
    this.useCategoriesError.set(null);
    try {
      await firstValueFrom(
        this.service.syncTriageUseCategories(
          triage.questionId,
          [...this.categoryDraft()].sort(),
          this.categoryDraftOutcome(),
        ),
      );
      this.triageRefreshToken.update((value) => value + 1);
    } catch (err) {
      this.useCategoriesError.set(toApiError(err));
    } finally {
      this.useCategoriesBusy.set(false);
    }
  }

  protected statusLabel(status: MuseumQuestionStatus): string {
    return STATUS_LABELS[status];
  }

  protected useCategoryLabel(category: string): string {
    return USE_CATEGORY_LABELS[category] ?? category.replaceAll('_', ' ').toLowerCase();
  }

  protected confidenceLabel(confidence: number): string {
    return `${Math.round(confidence * 100)}%`;
  }

  protected classifierKindLabel(kind: UseCategoryClassifierKind | null): string {
    return kind ? CLASSIFIER_KIND_LABELS[kind] : 'Classifier';
  }

  protected operationalClassifierLabel(kind: UseCategoryOperationalClassifier): string {
    return OPERATIONAL_CLASSIFIER_LABELS[kind];
  }

  protected scoreSourceLabel(source: UseCategoryScoreSource): string {
    return SCORE_SOURCE_LABELS[source];
  }

  protected categorySearchPolicyLabel(category: string): string {
    return USE_CATEGORY_SEARCH_POLICY_LABELS[category] ?? 'Review search need';
  }

  protected categorySearchPolicyClass(category: string): string {
    const policy = USE_CATEGORY_SEARCH_POLICY_LABELS[category];
    if (policy === 'Catalogue search') return 'use-category-card__policy--strong';
    if (policy === 'No catalogue search') return 'use-category-card__policy--muted';
    return 'use-category-card__policy--conditional';
  }

  protected highlightHtml(hit: ObjectTriageHit): SafeHtml {
    // Safe: highlightToSafeMarkup() escapes the whole string and only re-opens
    // <mark> for the backend's own <b> markers — never trust hit.highlight raw.
    return this.sanitizer.bypassSecurityTrustHtml(highlightToSafeMarkup(hit.highlight));
  }

  protected objectDisplayName(item: { english: string; portuguese: string }): string {
    return item.english.toLowerCase() === item.portuguese.toLowerCase()
      ? item.portuguese
      : `${item.portuguese} (${item.english})`;
  }

  protected matchCountLabel(count: number): string {
    if (count === 0) return 'No matches';
    if (count === 1) return '1 match';
    return `${count} matches`;
  }

  protected isTriageHitSelected(key: string): boolean {
    return this.selectedTriageHitKeys().has(key);
  }

  protected toggleTriageHitSelection(key: string): void {
    this.selectedTriageHitKeys.update((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  protected previousTriageHitsPage(item: TriageObjectResult): void {
    this.setTriageHitsPage(item.key, item.page - 1);
  }

  protected nextTriageHitsPage(item: TriageObjectResult): void {
    this.setTriageHitsPage(item.key, item.page + 1);
  }

  protected openHitDetails(row: TriageHitRow): void {
    this.selectedTriageHit.set(row);
  }

  protected closeHitDetails(): void {
    this.selectedTriageHit.set(null);
  }

  protected insertSelectedHitsIntoReply(): void {
    const selectedHtml = this.selectedHitsReplyHtml();
    if (!selectedHtml) return;

    this.insertHtmlIntoReply(selectedHtml);
  }

  protected insertSuggestedReplyIntoReply(suggestedReply: string | null): void {
    const reply = suggestedReply?.trim();
    if (!reply) return;

    this.insertHtmlIntoReply(`<p>${this.escapeHtml(reply)}</p>`);
  }

  private insertHtmlIntoReply(html: string): void {
    this.selectPanel('message');
    setTimeout(() => {
      const editor = this.replyEditor()?.nativeElement;
      if (!editor) return;

      const current = this.currentSanitizedAnswerBody();
      const next = current ? `${current}<p><br></p>${html}` : html;
      editor.innerHTML = this.sanitizeRichTextHtml(next);
      this.answerBody.set(this.currentSanitizedAnswerBody());
      editor.focus();
    });
  }

  protected formatDate(value: string | null): string {
    if (!value) return '-';
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: 'medium',
      timeStyle: 'short',
    }).format(new Date(value));
  }

  private normalizeTab(tab: string | undefined): QuestionDetailPanel {
    if (tab === 'history') return tab;
    if (tab === 'ai-assistance') return tab;
    return 'message';
  }

  private syncUrl(state: { tab?: QuestionDetailPanel }): void {
    const queryParams: Record<string, string | null> = {};
    if (state.tab !== undefined) {
      queryParams['tab'] = state.tab === 'message' ? null : state.tab;
    }
    void this.router
      .navigate([], {
        relativeTo: this.route,
        queryParams,
        queryParamsHandling: 'merge',
        replaceUrl: true,
      })
      .catch(() => undefined);
  }

  private setTriageHitsPage(key: string, page: number): void {
    this.triageHitPages.update((current) => {
      const next = new Map(current);
      next.set(key, Math.max(0, page));
      return next;
    });
  }

  private triageObjectKey(item: { english: string; portuguese: string }): string {
    return `${item.portuguese}:${item.english}`.toLowerCase();
  }

  private triageHitRow(match: ObjectTriageMatch, hit: ObjectTriageHit): TriageHitRow {
    return {
      key: `${this.triageObjectKey(match)}:${hit.collectionId}:${hit.fileName}:${hit.highlight}`,
      english: match.english,
      portuguese: match.portuguese,
      hit,
    };
  }

  private selectedHitsReplyHtml(): string {
    const rows = this.selectedTriageHitRows();
    if (!rows.length) return '';

    const items = rows
      .map(
        (row) =>
          `<li><strong>${this.escapeHtml(this.objectDisplayName(row))}</strong><br>` +
          `${this.escapeHtml(row.hit.collectionName)} - ${this.escapeHtml(row.hit.fileName)}<br>` +
          `${this.escapeHtml(this.highlightText(row.hit))}</li>`,
      )
      .join('');
    return `<p>Catalogue references found for your request:</p><ul>${items}</ul>`;
  }

  private highlightText(hit: ObjectTriageHit): string {
    const template = this.document.createElement('template');
    template.innerHTML = highlightToSafeMarkup(hit.highlight);
    return template.content.textContent?.trim() ?? '';
  }

  private escapeHtml(value: string): string {
    return value
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  private async run(operation: () => Observable<unknown>): Promise<void> {
    this.busy.set(true);
    this.actionError.set(null);
    try {
      await firstValueFrom(operation());
      this.detailRefreshToken.update((value) => value + 1);
    } catch (err) {
      this.actionError.set(toApiError(err));
    } finally {
      this.busy.set(false);
    }
  }

  private executeEditorCommand(command: ReplyEditorCommand): void {
    const editor = this.replyEditor()?.nativeElement;
    if (!editor) return;

    editor.focus();
    if (typeof this.document.execCommand === 'function') {
      this.document.execCommand(command, false);
    }
    this.answerBody.set(this.currentSanitizedAnswerBody());
  }

  private hasAnswerContent(): boolean {
    return (this.replyEditor()?.nativeElement.textContent?.trim() ?? '').length > 0;
  }

  private currentSanitizedAnswerBody(): string {
    return this.sanitizeRichTextHtml(
      this.replyEditor()?.nativeElement.innerHTML ?? this.answerBody(),
    );
  }

  private sanitizeRichTextHtml(html: string): string {
    const template = this.document.createElement('template');
    template.innerHTML = html;
    this.sanitizeRichTextChildren(template.content);
    return template.innerHTML.trim();
  }

  private sanitizeRichTextChildren(parent: ParentNode): void {
    for (const node of Array.from(parent.childNodes)) {
      if (node.nodeType === TEXT_NODE) continue;

      if (node.nodeType !== ELEMENT_NODE) {
        node.remove();
        continue;
      }

      const element = node as HTMLElement;
      const tagName = element.tagName.toUpperCase();

      if (BLOCKED_RICH_TEXT_TAGS.has(tagName)) {
        element.remove();
        continue;
      }

      this.sanitizeRichTextChildren(element);

      if (!ALLOWED_RICH_TEXT_TAGS.has(tagName)) {
        element.replaceWith(...Array.from(element.childNodes));
        continue;
      }

      for (const attribute of Array.from(element.attributes)) {
        element.removeAttribute(attribute.name);
      }
    }
  }
}
