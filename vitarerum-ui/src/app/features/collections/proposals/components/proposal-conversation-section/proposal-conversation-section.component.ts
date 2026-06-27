import { DOCUMENT, isPlatformBrowser } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  computed,
  effect,
  inject,
  input,
  output,
  PLATFORM_ID,
  signal,
  viewChild,
} from '@angular/core';

import { firstValueFrom } from 'rxjs';

import { ApiError, toApiError } from '@core/http/api-error.model';
import { ErrorMessageComponent } from '@shared/components/error-message/error-message.component';
import { LoadingStateComponent } from '@shared/components/loading-state/loading-state.component';

import {
  Message,
  MessageAttachment,
  ProposalDetail,
  RequestedObject,
} from '../../models/proposal.model';
import { PROPOSAL_API_SERVICE } from '../../services/proposal-api.service';
import { formatProposalDetailDateTime } from '../../proposal-detail.presentation';

export interface ReplyComposerPayload {
  readonly body: string;
  readonly files: readonly File[];
}

type ReplyEditorCommand = 'bold' | 'italic' | 'insertUnorderedList' | 'removeFormat';

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

@Component({
  selector: 'app-proposal-conversation-section',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [LoadingStateComponent, ErrorMessageComponent],
  templateUrl: './proposal-conversation-section.component.html',
  styleUrl: './proposal-conversation-section.component.scss',
})
export class ProposalConversationSectionComponent {
  private readonly document = inject(DOCUMENT);
  private readonly platformId = inject(PLATFORM_ID);
  private readonly proposalService = inject(PROPOSAL_API_SERVICE);
  private readonly replyEditor = viewChild<ElementRef<HTMLElement>>('replyEditor');

  readonly proposal = input.required<ProposalDetail>();
  readonly messages = input.required<readonly Message[]>();
  readonly messagesLoading = input.required<boolean>();
  readonly sendingMessage = input.required<boolean>();
  readonly messageError = input.required<ApiError | null>();
  readonly replyResetVersion = input.required<number>();
  readonly replyEyebrow = input('Staff response');
  readonly replyHeading = input('Reply to requester');
  readonly recipientEmail = input<string | null>(null);
  readonly canReply = input(true);
  readonly showRequestedObjectPicker = input(false);
  readonly showTriageAction = input(false);
  readonly replySubmitted = output<ReplyComposerPayload>();
  readonly triageRequested = output<Message>();

  protected readonly resolvedRecipientEmail = computed(
    () => this.recipientEmail() ?? this.proposal().requestedBy.user.email,
  );

  protected readonly selectedFiles = signal<readonly File[]>([]);
  protected readonly selectedRequestedObjectIds = signal<readonly string[]>([]);
  protected readonly insertedRequestedObjectIds = signal<readonly string[]>([]);
  protected readonly requestedObjectPickerExpanded = signal(false);
  protected readonly replyBody = signal('');
  protected readonly hasSelectedRequestedObjects = computed(
    () => this.selectedRequestedObjectIds().length > 0,
  );
  protected readonly formatDateTime = formatProposalDetailDateTime;

  // documentId currently downloading, plus the last download error (per section).
  protected readonly downloadingDocumentId = signal<string | null>(null);
  protected readonly downloadError = signal<ApiError | null>(null);
  private readonly resetReplyOnVersionChange = effect(() => {
    if (this.replyResetVersion() > 0) this.clearReply();
  });

  protected messageIcon(message: Message): string {
    return this.isRequesterMessage(message) ? 'pi pi-user' : 'pi pi-briefcase';
  }

  protected messageRoleLabel(message: Message): string {
    if (this.isRequesterMessage(message)) return 'Requester';
    return this.proposal().assignedTo?.group.replace('_', ' ') ?? 'Staff';
  }

  protected isRequesterMessage(message: Message): boolean {
    return message.sender === this.proposal().requestedBy.user.email;
  }

  protected async downloadAttachment(attachment: MessageAttachment): Promise<void> {
    if (this.downloadingDocumentId()) return;

    this.downloadingDocumentId.set(attachment.documentId);
    this.downloadError.set(null);
    try {
      const blob = await firstValueFrom(
        this.proposalService.downloadDocument(this.proposal().id, attachment.documentId),
      );
      this.saveBlob(blob, attachment.fileName);
    } catch (err) {
      this.downloadError.set(toApiError(err));
    } finally {
      this.downloadingDocumentId.set(null);
    }
  }

  protected requestTriage(message: Message): void {
    this.triageRequested.emit(message);
  }

  protected sanitizeMessageBody(body: string): string {
    return this.sanitizeRichTextHtml(body);
  }

  private saveBlob(blob: Blob, fileName: string): void {
    if (!isPlatformBrowser(this.platformId)) return;

    const url = URL.createObjectURL(blob);
    const anchor = this.document.createElement('a');
    anchor.href = url;
    anchor.download = fileName;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  protected onReplyInput(event: Event): void {
    const editor = event.target as HTMLElement;
    this.replyBody.set(this.sanitizeRichTextHtml(editor.innerHTML));
    this.syncInsertedRequestedObjects(editor);
  }

  protected isRequestedObjectSelected(requestedObjectId: string): boolean {
    return this.selectedRequestedObjectIds().includes(requestedObjectId);
  }

  protected isRequestedObjectInserted(requestedObjectId: string): boolean {
    return this.insertedRequestedObjectIds().includes(requestedObjectId);
  }

  protected toggleRequestedObjectPicker(): void {
    this.requestedObjectPickerExpanded.update((expanded) => !expanded);
  }

  protected onRequestedObjectSelectionChange(requestedObjectId: string, event: Event): void {
    const checked = (event.target as HTMLInputElement).checked;
    this.selectedRequestedObjectIds.update((selectedIds) =>
      checked
        ? [...selectedIds, requestedObjectId]
        : selectedIds.filter((id) => id !== requestedObjectId),
    );
  }

  protected insertSelectedRequestedObjects(): void {
    const editor = this.replyEditor()?.nativeElement;
    if (!editor) return;

    const selectedIds = new Set(this.selectedRequestedObjectIds());
    const insertedIds = new Set(this.insertedRequestedObjectIds());
    const objectsToInsert = this.proposal().requestedObjects.filter(
      (requestedObject) =>
        selectedIds.has(requestedObject.id) && !insertedIds.has(requestedObject.id),
    );
    if (!objectsToInsert.length) return;

    if (editor.textContent?.trim()) {
      const separator = this.document.createElement('p');
      separator.append(this.document.createElement('br'));
      editor.append(separator);
    }

    const heading = this.document.createElement('p');
    const headingText = this.document.createElement('strong');
    headingText.textContent = 'Requested objects';
    heading.append(headingText);

    const list = this.document.createElement('ul');
    for (const requestedObject of objectsToInsert) {
      const item = this.document.createElement('li');
      item.dataset['requestedObjectId'] = requestedObject.id;
      item.textContent = this.requestedObjectMessageText(requestedObject);
      list.append(item);
      insertedIds.add(requestedObject.id);
    }

    editor.append(heading, list);
    this.insertedRequestedObjectIds.set([...insertedIds]);
    this.selectedRequestedObjectIds.set([]);
    this.syncReplyBody();
    editor.focus();
  }

  protected applyEditorCommand(command: 'bold' | 'italic' | 'insertUnorderedList'): void {
    this.executeEditorCommand(command);
  }

  protected clearReplyFormatting(): void {
    this.executeEditorCommand('removeFormat');
  }

  protected onFilesSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    const files = Array.from(input.files ?? []);
    this.selectedFiles.update((current) => [...current, ...files]);
    input.value = '';
  }

  protected removeSelectedFile(index: number): void {
    this.selectedFiles.update((files) => files.filter((_, i) => i !== index));
  }

  protected canSendReply(): boolean {
    return this.hasReplyContent() && !this.sendingMessage();
  }

  protected sendReply(): void {
    if (!this.canSendReply()) return;

    const body = this.currentSanitizedReplyBody();
    this.replyBody.set(body);
    this.replySubmitted.emit({
      body,
      files: this.selectedFiles(),
    });
  }

  private syncReplyBody(): void {
    this.replyBody.set(this.currentSanitizedReplyBody());
  }

  private executeEditorCommand(command: ReplyEditorCommand): void {
    const editor = this.replyEditor()?.nativeElement;
    if (!editor) return;

    editor.focus();
    if (isPlatformBrowser(this.platformId) && typeof this.document.execCommand === 'function') {
      this.document.execCommand(command, false);
    }
    this.syncReplyBody();
  }

  private clearReply(): void {
    const editor = this.replyEditor()?.nativeElement;
    if (editor) editor.innerHTML = '';
    this.replyBody.set('');
    this.selectedFiles.set([]);
    this.selectedRequestedObjectIds.set([]);
    this.insertedRequestedObjectIds.set([]);
    this.requestedObjectPickerExpanded.set(false);
  }

  private requestedObjectMessageText(requestedObject: RequestedObject): string {
    const reference = requestedObject.objectReference;
    const title = reference.displayTitle ?? reference.objectName ?? 'Untitled object';
    const details = [
      reference.objectName && reference.objectName !== title ? reference.objectName : null,
      reference.briefDescriptionSnapshot,
      requestedObject.description,
    ].filter((value): value is string => Boolean(value?.trim()));

    return `${reference.inventoryNumber} — ${title}${details.length ? ` (${details.join('; ')})` : ''}`;
  }

  private syncInsertedRequestedObjects(editor: HTMLElement): void {
    const insertedIds = Array.from(
      editor.querySelectorAll<HTMLElement>('[data-requested-object-id]'),
    )
      .map((element) => element.dataset['requestedObjectId'])
      .filter((id): id is string => Boolean(id));
    this.insertedRequestedObjectIds.set(insertedIds);
  }

  private hasReplyContent(): boolean {
    const text = this.replyEditor()?.nativeElement.textContent?.trim() ?? '';
    return text.length > 0 || this.selectedFiles().length > 0;
  }

  private currentSanitizedReplyBody(): string {
    return this.sanitizeRichTextHtml(
      this.replyEditor()?.nativeElement.innerHTML ?? this.replyBody(),
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
