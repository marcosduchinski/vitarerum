import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  input,
  output,
  resource,
  signal,
} from '@angular/core';
import { DatePipe } from '@angular/common';
import { RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { ApiError, toApiError } from '@core/http/api-error.model';
import { IntendedUse } from '@shared/models/collection-use-status.model';
import { ErrorMessageComponent } from '@shared/components/error-message/error-message.component';
import { LoadingStateComponent } from '@shared/components/loading-state/loading-state.component';
import { PROPOSAL_API_SERVICE } from '@features/collections/proposals/services/proposal-api.service';

import { ProposalRecordSearchResultsComponent } from '../proposal-record-search-results/proposal-record-search-results.component';
import { CatalogRecordSnapshot, IntendedUseSuggestion } from '../../models/proposal-chat.model';
import { PROPOSAL_CHAT_SERVICE } from '../../services/proposal-chat.service';

type AgentTaskId = 'intended-use' | 'find-documents' | 'search-records' | 'draft-reply';

/**
 * A task the curator can delegate to the assistant. Future capabilities — locating
 * documents to return, pulling figures from spreadsheets, drafting a reply — register
 * here and flow through the same turn pipeline. Adding one means flipping `available`
 * and handling its result branch in {@link dispatch}; the thread shell is untouched.
 */
interface AgentTask {
  readonly id: AgentTaskId;
  readonly label: string;
  readonly icon: string;
  readonly hint: string;
  /** What the curator's turn reads as when this task is delegated. */
  readonly utterance: string;
  readonly available: boolean;
}

interface TurnBase {
  readonly id: string;
  readonly at: string;
}
interface UserTurn extends TurnBase {
  readonly role: 'user';
  readonly text: string;
}
interface PendingTurn extends TurnBase {
  readonly role: 'pending';
  readonly task: string;
}
interface ErrorTurn extends TurnBase {
  readonly role: 'error';
  readonly task: string;
  readonly error: ApiError;
}
interface NoteTurn extends TurnBase {
  readonly role: 'note';
  readonly text: string;
}
interface IntendedUseTurn extends TurnBase {
  readonly role: 'intended-use';
  readonly suggestion: IntendedUseSuggestion;
}
interface SearchRecordsTurn extends TurnBase {
  readonly role: 'search-records';
  readonly records: readonly CatalogRecordSnapshot[];
}

type ChatTurn = UserTurn | PendingTurn | ErrorTurn | NoteTurn | IntendedUseTurn | SearchRecordsTurn;

const SIMULATED_CATALOG_RECORDS: readonly CatalogRecordSnapshot[] = [
  {
    inventoryNumber: 'MNHN-MAM-00421',
    displayTitle: 'Lynx pardinus study skin',
    objectName: 'Zoological study skin',
    briefDescriptionSnapshot:
      'Historic Iberian lynx reference specimen prepared for the mammalogy collection.',
    category: 'mammalogy',
    description: 'Selected for comparative research on Lynx pardinus morphology.',
  },
  {
    inventoryNumber: 'MNHN-OST-00108',
    displayTitle: 'Lynx pardinus skull',
    objectName: 'Osteological specimen',
    briefDescriptionSnapshot: 'Adult Iberian lynx skull with associated collection documentation.',
    category: 'osteology',
    description: 'Selected as an osteological reference for Lynx pardinus research.',
  },
  {
    inventoryNumber: 'ARC-PHO-01977',
    displayTitle: 'Lynx pardinus field photograph',
    objectName: 'Archival photograph',
    briefDescriptionSnapshot:
      'Field photograph documenting an Iberian lynx in Mediterranean scrub habitat.',
    category: 'photographic archive',
    description: 'Selected as contextual documentation of Lynx pardinus habitat.',
  },
];

@Component({
  selector: 'app-proposal-chat-panel',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    DatePipe,
    RouterLink,
    LoadingStateComponent,
    ErrorMessageComponent,
    ProposalRecordSearchResultsComponent,
  ],
  templateUrl: './proposal-chat-panel.component.html',
  styleUrl: './proposal-chat-panel.component.scss',
})
export class ProposalChatPanelComponent {
  private readonly proposalChat = inject(PROPOSAL_CHAT_SERVICE);
  private readonly proposalService = inject(PROPOSAL_API_SERVICE);

  readonly conversationId = input.required<string>();
  readonly messageId = input.required<string>();
  readonly embedded = input(false);
  // Overridable so tests can disable the short "assistant is working" pause.
  readonly thinkingDelayMs = input(650);
  readonly applied = output<void>();
  readonly requestedObjectsAdded = output<void>();

  protected readonly contextResource = resource({
    params: () => ({ conversationId: this.conversationId(), messageId: this.messageId() }),
    loader: ({ params }) => firstValueFrom(this.proposalChat.getContext(params)),
  });

  protected readonly context = computed(() => this.contextResource.value() ?? null);
  protected readonly contextError = computed<ApiError | null>(() => {
    const err = this.contextResource.error();
    return err ? toApiError(err) : null;
  });

  /** The delegated conversation, oldest first. Mixed turn kinds; render via @switch. */
  protected readonly turns = signal<readonly ChatTurn[]>([]);
  protected readonly busy = computed(() => this.turns().some((turn) => turn.role === 'pending'));

  private readonly applyingId = signal<string | null>(null);
  private readonly appliedIds = signal<ReadonlySet<string>>(new Set());
  protected readonly applyError = signal<ApiError | null>(null);
  private readonly savingRecordsTurnId = signal<string | null>(null);
  private readonly savedRecordsTurnIds = signal<ReadonlySet<string>>(new Set());
  protected readonly recordsError = signal<ApiError | null>(null);

  /** Announced to assistive tech as turns resolve (the visual thread is the rest). */
  protected readonly liveMessage = signal('');

  protected readonly tasks: readonly AgentTask[] = [
    {
      id: 'intended-use',
      label: 'Analyse intended use',
      icon: 'pi-compass',
      hint: 'Read the request and suggest a use classification',
      utterance: 'Analyse this message for its intended use.',
      available: true,
    },
    {
      id: 'find-documents',
      label: 'Find documents to send',
      icon: 'pi-folder-open',
      hint: 'Locate files to return to the requester',
      utterance: 'Find documents I can send back to the requester.',
      available: false,
    },
    {
      id: 'search-records',
      label: 'Search records',
      icon: 'pi-database',
      hint: 'Search the demonstration catalog for matching collection objects',
      utterance: 'Search the catalog for collection objects related to this request.',
      available: true,
    },
    {
      id: 'draft-reply',
      label: 'Draft a reply',
      icon: 'pi-pencil',
      hint: 'Compose a message back to the requester',
      utterance: 'Draft a reply to the requester.',
      available: false,
    },
  ];

  private seq = 0;

  protected async dispatch(task: AgentTask): Promise<void> {
    if (!task.available || this.busy()) return;

    this.appendTurn({ id: this.nextId(), at: this.now(), role: 'user', text: task.utterance });
    const pendingId = this.nextId();
    this.appendTurn({ id: pendingId, at: this.now(), role: 'pending', task: task.label });
    this.applyError.set(null);
    this.recordsError.set(null);
    this.liveMessage.set(`${task.label}: the assistant is working.`);

    try {
      switch (task.id) {
        case 'intended-use': {
          await this.delay(this.thinkingDelayMs());
          const suggestion = await firstValueFrom(
            this.proposalChat.suggestIntendedUse({
              conversationId: this.conversationId(),
              messageId: this.messageId(),
            }),
          );
          this.replaceTurn(pendingId, {
            id: pendingId,
            at: this.now(),
            role: 'intended-use',
            suggestion,
          });
          this.liveMessage.set(
            `Suggested ${this.formatUseType(suggestion.intendedUse.useType)} at ` +
              `${this.confidencePercent(suggestion.confidence)}% confidence.`,
          );
          break;
        }
        case 'search-records': {
          await this.delay(this.thinkingDelayMs());
          this.replaceTurn(pendingId, {
            id: pendingId,
            at: this.now(),
            role: 'search-records',
            records: SIMULATED_CATALOG_RECORDS,
          });
          this.liveMessage.set('Search complete. Three Lynx pardinus records were found.');
          break;
        }
        default:
          // Unavailable tasks never dispatch; this guards future ids without a branch.
          this.replaceTurns((turns) => turns.filter((turn) => turn.id !== pendingId));
          break;
      }
    } catch (err) {
      this.replaceTurn(pendingId, {
        id: pendingId,
        at: this.now(),
        role: 'error',
        task: task.label,
        error: toApiError(err),
      });
      this.liveMessage.set(`${task.label} could not be completed.`);
    }
  }

  protected async apply(turn: IntendedUseTurn): Promise<void> {
    const context = this.context();
    if (!context || this.applyingId() || this.isApplied(turn) || this.matchesCurrent(turn)) return;

    this.applyingId.set(turn.id);
    this.applyError.set(null);

    try {
      await firstValueFrom(
        this.proposalService.updateProposal(context.proposal.proposalId, {
          intendedUse: turn.suggestion.intendedUse,
        }),
      );
      this.appliedIds.update((ids) => new Set(ids).add(turn.id));
      this.appendTurn({
        id: this.nextId(),
        at: this.now(),
        role: 'note',
        text: `Applied “${this.formatUseType(turn.suggestion.intendedUse.useType)}” to the proposal.`,
      });
      this.liveMessage.set('Suggestion applied to the proposal.');
      this.applied.emit();
      this.contextResource.reload();
    } catch (err) {
      this.applyError.set(toApiError(err));
    } finally {
      this.applyingId.set(null);
    }
  }

  protected retryContext(): void {
    this.turns.set([]);
    this.appliedIds.set(new Set());
    this.savingRecordsTurnId.set(null);
    this.savedRecordsTurnIds.set(new Set());
    this.applyError.set(null);
    this.recordsError.set(null);
    this.liveMessage.set('');
    this.contextResource.reload();
  }

  protected matchesCurrent(turn: IntendedUseTurn): boolean {
    const context = this.context();
    if (!context) return false;
    return this.sameIntendedUse(context.proposal.intendedUse, turn.suggestion.intendedUse);
  }

  protected isApplied(turn: IntendedUseTurn): boolean {
    return this.appliedIds().has(turn.id);
  }

  protected isApplying(turn: IntendedUseTurn): boolean {
    return this.applyingId() === turn.id;
  }

  protected async addRequestedObjects(
    turn: SearchRecordsTurn,
    records: readonly CatalogRecordSnapshot[],
  ): Promise<void> {
    const context = this.context();
    if (
      !context ||
      !records.length ||
      !this.canAddRequestedObjects() ||
      this.savingRecordsTurnId() ||
      this.isRecordsSaved(turn)
    ) {
      return;
    }

    this.savingRecordsTurnId.set(turn.id);
    this.recordsError.set(null);

    try {
      await firstValueFrom(
        this.proposalService.addRequestedObjects(context.proposal.proposalId, {
          objects: records,
        }),
      );
      this.savedRecordsTurnIds.update((ids) => new Set(ids).add(turn.id));
      this.appendTurn({
        id: this.nextId(),
        at: this.now(),
        role: 'note',
        text: `${records.length} ${records.length === 1 ? 'object was' : 'objects were'} added to the proposal.`,
      });
      this.liveMessage.set(
        `${records.length} selected ${records.length === 1 ? 'object was' : 'objects were'} added to the proposal.`,
      );
      this.requestedObjectsAdded.emit();
    } catch (err) {
      this.recordsError.set(toApiError(err));
    } finally {
      this.savingRecordsTurnId.set(null);
    }
  }

  protected canAddRequestedObjects(): boolean {
    const status = this.context()?.proposal.status;
    return status === 'SUBMITTED' || status === 'PENDING';
  }

  protected isSavingRecords(turn: SearchRecordsTurn): boolean {
    return this.savingRecordsTurnId() === turn.id;
  }

  protected isRecordsSaved(turn: SearchRecordsTurn): boolean {
    return this.savedRecordsTurnIds().has(turn.id);
  }

  protected formatUseType(value: string): string {
    return value.replaceAll('_', ' ').toLowerCase();
  }

  protected formatStatus(value: string): string {
    return value.replaceAll('_', ' ').toLowerCase();
  }

  protected confidencePercent(value: number): number {
    return Math.round(Math.max(0, Math.min(1, value)) * 100);
  }

  protected sourceLabel(source: IntendedUseSuggestion['source']): string {
    return `${source.conversationId} / ${source.messageId}`;
  }

  // Narrowing helpers for the template's @switch (keeps the markup free of casts).
  protected asIntendedUse(turn: ChatTurn): IntendedUseTurn {
    return turn as IntendedUseTurn;
  }
  protected asSearchRecords(turn: ChatTurn): SearchRecordsTurn {
    return turn as SearchRecordsTurn;
  }
  protected asError(turn: ChatTurn): ErrorTurn {
    return turn as ErrorTurn;
  }

  private appendTurn(turn: ChatTurn): void {
    this.turns.update((turns) => [...turns, turn]);
  }

  private replaceTurn(id: string, turn: ChatTurn): void {
    this.turns.update((turns) => turns.map((existing) => (existing.id === id ? turn : existing)));
  }

  private replaceTurns(project: (turns: readonly ChatTurn[]) => readonly ChatTurn[]): void {
    this.turns.update((turns) => project(turns));
  }

  private sameIntendedUse(a: IntendedUse, b: IntendedUse): boolean {
    return a.useType === b.useType && a.description.trim() === b.description.trim();
  }

  private nextId(): string {
    return `turn-${++this.seq}`;
  }

  private now(): string {
    return new Date().toISOString();
  }

  private delay(ms: number): Promise<void> {
    return ms > 0 ? new Promise<void>((resolve) => setTimeout(resolve, ms)) : Promise.resolve();
  }
}
