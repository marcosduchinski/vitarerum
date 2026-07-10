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
} from '../../models/museum-question-triage.model';
import { MuseumQuestion, MuseumQuestionStatus } from '../../models/museum-question.model';
import { MUSEUM_QUESTION_MANAGEMENT_SERVICE } from '../../services/museum-question-management.service';

type QuestionDetailPanel = 'message' | 'ai-assistance';
type ReplyEditorCommand = 'bold' | 'italic' | 'insertUnorderedList' | 'removeFormat';

interface TriageHitRow {
  readonly key: string;
  readonly english: string;
  readonly portuguese: string;
  readonly hit: ObjectTriageHit;
}

interface TriageObjectResult extends MentionedObject {
  readonly key: string;
  /** Full merged/deduplicated list — used for the match count and for
   * "Add to reply" selection, which must work across every page. */
  readonly hits: readonly TriageHitRow[];
  /** Just the current page's slice of `hits`, for rendering. */
  readonly pagedHits: readonly TriageHitRow[];
  readonly page: number;
  readonly totalPages: number;
}

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

  protected readonly questionResource = resource({
    params: () => ({ id: this.id(), refresh: this.detailRefreshToken() }),
    loader: ({ params }) => firstValueFrom(this.service.get(params.id)),
  });

  protected readonly question = computed(() => this.questionResource.value() ?? null);
  protected readonly questionError = computed<ApiError | null>(() => {
    const err = this.questionResource.error();
    return err ? toApiError(err) : null;
  });

  protected readonly triageResource = resource({
    params: () => ({ id: this.id(), refresh: this.triageRefreshToken() }),
    loader: ({ params }) => firstValueFrom(this.service.getTriage(params.id)),
  });

  protected readonly triage = computed<MuseumQuestionTriage | null>(
    () => this.triageResource.value() ?? null,
  );
  protected readonly triageResourceError = computed<ApiError | null>(() => {
    const err = this.triageResource.error();
    return err ? toApiError(err) : null;
  });
  protected readonly triageObjectResults = computed<readonly TriageObjectResult[]>(() => {
    const pages = this.triageHitPages();
    return (this.triage()?.objectMatches ?? []).map((match) => {
      const key = this.triageObjectKey(match);
      const hits = match.hits.map((hit) => this.triageHitRow(match, hit));
      const totalPages = Math.max(1, Math.ceil(hits.length / TRIAGE_HITS_PAGE_SIZE));
      const page = Math.min(pages.get(key) ?? 0, totalPages - 1);
      return {
        key,
        english: match.english,
        portuguese: match.portuguese,
        hits,
        page,
        totalPages,
        pagedHits: hits.slice(page * TRIAGE_HITS_PAGE_SIZE, (page + 1) * TRIAGE_HITS_PAGE_SIZE),
      };
    });
  });
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

  protected cancelConfirmations(): void {
    this.confirmOutOfScope.set(false);
    this.confirmClose.set(false);
  }

  protected statusLabel(status: MuseumQuestionStatus): string {
    return STATUS_LABELS[status];
  }

  protected highlightHtml(hit: ObjectTriageHit): SafeHtml {
    // Safe: highlightToSafeMarkup() escapes the whole string and only re-opens
    // <mark> for the backend's own <b> markers — never trust hit.highlight raw.
    return this.sanitizer.bypassSecurityTrustHtml(highlightToSafeMarkup(hit.highlight));
  }

  protected objectDisplayName(item: MentionedObject): string {
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

    this.selectPanel('message');
    setTimeout(() => {
      const editor = this.replyEditor()?.nativeElement;
      if (!editor) return;

      const current = this.currentSanitizedAnswerBody();
      const next = current ? `${current}<p><br></p>${selectedHtml}` : selectedHtml;
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

  private triageObjectKey(match: ObjectTriageMatch): string {
    return `${match.portuguese}:${match.english}`.toLowerCase();
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
