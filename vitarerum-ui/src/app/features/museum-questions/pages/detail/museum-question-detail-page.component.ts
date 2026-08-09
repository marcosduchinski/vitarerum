import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
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
import { firstValueFrom, Observable } from 'rxjs';

import { ApiError, toApiError } from '@core/http/api-error.model';
import { EmptyStateComponent } from '@shared/components/empty-state/empty-state.component';
import { ErrorMessageComponent } from '@shared/components/error-message/error-message.component';
import { LoadingStateComponent } from '@shared/components/loading-state/loading-state.component';

import {
  MuseumQuestion,
  MuseumQuestionAttachment,
  MuseumQuestionListItem,
  MuseumQuestionPage,
  MuseumQuestionStatus,
} from '../../models/museum-question.model';
import { MUSEUM_QUESTION_MANAGEMENT_SERVICE } from '../../services/museum-question-management.service';

type QuestionDetailPanel = 'message' | 'history';
type ReplyEditorCommand = 'bold' | 'italic' | 'insertUnorderedList' | 'removeFormat';

interface AttachmentPreview {
  readonly url: string | null;
  readonly error: boolean;
}

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
  imports: [RouterLink, LoadingStateComponent, ErrorMessageComponent, EmptyStateComponent],
  templateUrl: './museum-question-detail-page.component.html',
  styleUrl: './museum-question-detail-page.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class MuseumQuestionDetailPageComponent {
  private readonly document = inject(DOCUMENT);
  private readonly service = inject(MUSEUM_QUESTION_MANAGEMENT_SERVICE);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);
  private readonly destroyRef = inject(DestroyRef);
  private readonly replyEditor = viewChild<ElementRef<HTMLElement>>('replyEditor');
  private readonly attachmentObjectUrls = new Set<string>();

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

  protected readonly attachmentPreviewResource = resource<
    ReadonlyMap<string, AttachmentPreview>,
    {
      readonly questionId: string | null;
      readonly attachments: readonly MuseumQuestionAttachment[];
    }
  >({
    params: () => {
      const question = this.question();
      return {
        questionId: question?.id ?? null,
        attachments: question?.attachments ?? [],
      };
    },
    loader: async ({ params }) => {
      this.revokeAttachmentObjectUrls();
      if (!params.questionId || !params.attachments.length) return new Map();
      const entries: readonly (readonly [string, AttachmentPreview])[] = await Promise.all(
        params.attachments.map(async (attachment) => {
          try {
            const blob = await firstValueFrom(
              this.service.getAttachment(params.questionId!, attachment),
            );
            const url = URL.createObjectURL(blob);
            this.attachmentObjectUrls.add(url);
            return [attachment.id, { url, error: false }] as const satisfies readonly [
              string,
              AttachmentPreview,
            ];
          } catch {
            return [attachment.id, { url: null, error: true }] as const satisfies readonly [
              string,
              AttachmentPreview,
            ];
          }
        }),
      );
      return new Map(entries);
    },
  });

  protected readonly historyError = computed<ApiError | null>(() => {
    const err = this.historyResource.error();
    return err ? toApiError(err) : null;
  });
  protected readonly previousQuestions = computed<readonly MuseumQuestionListItem[]>(() => {
    const question = this.question();
    const page = this.historyResource.value();
    if (!question || !page) return [];
    return page.content
      .filter((item) => item.id !== question.id)
      .sort((a, b) => b.createdAt.localeCompare(a.createdAt));
  });
  protected readonly previousQuestionsTotal = computed(() => {
    const question = this.question();
    const page = this.historyResource.value();
    if (!question || !page) return 0;
    return Math.max(0, page.totalElements - 1);
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

  protected cancelConfirmations(): void {
    this.confirmOutOfScope.set(false);
    this.confirmClose.set(false);
  }

  protected statusLabel(status: MuseumQuestionStatus): string {
    return STATUS_LABELS[status];
  }

  protected dueLabel(question: MuseumQuestion): string {
    const due = this.formatDate(question.responseDueAt);
    return question.responseOverdue ? `Overdue · ${due}` : `Due ${due}`;
  }

  protected attachmentPreview(attachment: MuseumQuestionAttachment): AttachmentPreview {
    return (
      this.attachmentPreviewResource.value()?.get(attachment.id) ?? { url: null, error: false }
    );
  }

  protected formatDate(value: string | null): string {
    if (!value) return '-';
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: 'medium',
      timeStyle: 'short',
    }).format(new Date(value));
  }

  protected formatBytes(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    const mib = bytes / (1024 * 1024);
    if (mib >= 1) return `${mib.toFixed(mib >= 10 ? 0 : 1)} MB`;
    return `${Math.ceil(bytes / 1024)} KB`;
  }

  constructor() {
    this.destroyRef.onDestroy(() => this.revokeAttachmentObjectUrls());
  }

  private normalizeTab(tab: string | undefined): QuestionDetailPanel {
    return tab === 'history' ? 'history' : 'message';
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

  private revokeAttachmentObjectUrls(): void {
    for (const url of this.attachmentObjectUrls) {
      URL.revokeObjectURL(url);
    }
    this.attachmentObjectUrls.clear();
  }
}
