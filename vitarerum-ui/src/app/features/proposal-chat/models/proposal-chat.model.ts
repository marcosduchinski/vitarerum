import { IntendedUse, ProposalStatus } from '@shared/models/collection-use-status.model';

export interface ProposalChatContextQuery {
  readonly conversationId: string;
  readonly messageId: string;
}

export type SuggestIntendedUseRequest = ProposalChatContextQuery;

export interface ProposalChatFocusMessage {
  readonly messageId: string;
  readonly sentAt: string;
  readonly sender: string;
  readonly subject: string;
  readonly body: string;
}

export interface ProposalChatProposalSummary {
  readonly proposalId: string;
  readonly referenceNumber: string;
  readonly title: string;
  readonly status: ProposalStatus;
  readonly intendedUse: IntendedUse;
}

export interface ProposalChatContext {
  readonly conversationId: string;
  readonly focusMessage: ProposalChatFocusMessage;
  readonly proposal: ProposalChatProposalSummary;
}

export interface IntendedUseSuggestionSource {
  readonly conversationId: string;
  readonly messageId: string;
}

export interface IntendedUseSuggestion {
  readonly intendedUse: IntendedUse;
  readonly confidence: number;
  readonly rationale: string;
  readonly source: IntendedUseSuggestionSource;
}

export interface IntendedUseSuggestionResponse {
  readonly suggestion: IntendedUseSuggestion;
}

export interface CatalogRecordSnapshot {
  readonly inventoryNumber: string;
  readonly displayTitle: string;
  readonly objectName: string;
  readonly briefDescriptionSnapshot: string | null;
  readonly category: string;
  readonly description: string;
}
