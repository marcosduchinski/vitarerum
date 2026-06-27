import { inject, Injectable } from '@angular/core';
import { IDENTITY_SERVICE } from '@core/auth/identity.service';
import { IntendedUse, UseType } from '@shared/models/collection-use-status.model';
import { firstValueFrom, from, Observable } from 'rxjs';

import {
  IntendedUseSuggestion,
  ProposalChatContext,
  ProposalChatContextQuery,
  SuggestIntendedUseRequest,
} from '../models/proposal-chat.model';
import { Message, ProposalDetail } from '../../collections/proposals/models/proposal.model';
import { PROPOSAL_API_SERVICE } from '../../collections/proposals/services/proposal-api.service';

interface WeightedUseType {
  readonly useType: UseType;
  readonly score: number;
  readonly evidence: readonly string[];
}

@Injectable()
export class ProposalChatServiceMock {
  private readonly identity = inject(IDENTITY_SERVICE);
  private readonly proposalService = inject(PROPOSAL_API_SERVICE);

  getContext(query: ProposalChatContextQuery): Observable<ProposalChatContext> {
    return from(this.getContextAsync(query));
  }

  suggestIntendedUse(request: SuggestIntendedUseRequest): Observable<IntendedUseSuggestion> {
    return from(this.suggestIntendedUseAsync(request));
  }

  private async getContextAsync(query: ProposalChatContextQuery): Promise<ProposalChatContext> {
    this.assertStaff();
    const { proposal, message } = await this.resolveFocus(query);
    return this.toContext(proposal, message);
  }

  private async suggestIntendedUseAsync(
    request: SuggestIntendedUseRequest,
  ): Promise<IntendedUseSuggestion> {
    this.assertStaff();
    const { proposal, message } = await this.resolveFocus(request);
    if (!message.body.trim()) {
      throw this.apiError(422, 'EMPTY_MESSAGE_BODY', 'The focus message has no analysable content');
    }

    const suggestion = this.triageEmail(proposal, message);
    return {
      intendedUse: suggestion.intendedUse,
      confidence: suggestion.confidence,
      rationale: suggestion.rationale,
      source: {
        conversationId: request.conversationId,
        messageId: request.messageId,
      },
    };
  }

  private async resolveFocus(query: ProposalChatContextQuery): Promise<{
    readonly proposal: ProposalDetail;
    readonly message: Message;
  }> {
    const proposalsPage = await firstValueFrom(this.proposalService.listProposals({ size: 500 }));
    const proposalDetails = await Promise.all(
      proposalsPage.content.map((item) =>
        firstValueFrom(this.proposalService.getProposal(item.id)),
      ),
    );
    const proposal = proposalDetails.find((item) => item.conversationId === query.conversationId);

    if (!proposal) {
      throw this.apiError(
        404,
        'CONVERSATION_NOT_FOUND',
        `No conversation found with id ${query.conversationId}`,
      );
    }

    const conversation = await firstValueFrom(this.proposalService.getConversation(proposal.id));
    const message = conversation.messages.find((item) => item.id === query.messageId);

    if (!message) {
      throw this.apiError(
        404,
        'MESSAGE_NOT_FOUND',
        `No message found with id ${query.messageId} in conversation ${query.conversationId}`,
      );
    }

    return { proposal, message };
  }

  private toContext(proposal: ProposalDetail, message: Message): ProposalChatContext {
    return {
      conversationId: proposal.conversationId,
      focusMessage: {
        messageId: message.id,
        sentAt: message.sentAt,
        sender: message.sender,
        subject: message.subject,
        body: message.body,
      },
      proposal: {
        proposalId: proposal.id,
        referenceNumber: proposal.referenceNumber,
        title: proposal.title,
        status: proposal.status,
        intendedUse: this.intendedUseOf(proposal),
      },
    };
  }

  private triageEmail(
    proposal: ProposalDetail,
    message: Message,
  ): {
    readonly intendedUse: IntendedUse;
    readonly confidence: number;
    readonly rationale: string;
  } {
    const text = [
      proposal.title,
      proposal.intendedUse?.description ?? '',
      message.subject,
      message.body,
    ]
      .join(' ')
      .toLowerCase();
    const scores: readonly WeightedUseType[] = [
      this.scoreUseType(text, 'EXHIBITION', [
        'exhibition',
        'display',
        'public',
        'education',
        'loan',
      ]),
      this.scoreUseType(text, 'IN_SITU_VISIT', [
        'access',
        'visit',
        'research',
        'study',
        'catalogue',
        'catalogues',
        'notebook',
        'notebooks',
        'records',
        'specimen',
      ]),
      this.scoreUseType(text, 'OTHER', ['other', 'mixed', 'unclear', 'general']),
    ];
    const currentUse = this.intendedUseOf(proposal);
    const fallback: WeightedUseType = {
      useType: currentUse.useType,
      score: 1,
      evidence: [`Existing proposal type is ${currentUse.useType.replace('_', ' ')}.`],
    };
    const best = [...scores, fallback].sort((a, b) => b.score - a.score)[0];
    const confidence = Math.min(0.98, Math.max(0.35, 0.45 + best.score * 0.13));
    const description =
      best.evidence.length > 0
        ? `Suggested from the focus message: ${best.evidence.join(' ')}`
        : currentUse.description;

    return {
      intendedUse: {
        useType: best.useType,
        description,
      },
      confidence: Number(confidence.toFixed(2)),
      rationale: `The selected message most closely matches ${this.formatUseType(best.useType)} because ${
        best.evidence.length
          ? best.evidence.join(' ')
          : 'it follows the proposal current intended use.'
      }`,
    };
  }

  private scoreUseType(
    text: string,
    useType: UseType,
    keywords: readonly string[],
  ): WeightedUseType {
    const evidence = keywords
      .filter((keyword) => text.includes(keyword))
      .map((keyword) => `matched "${keyword}"`);
    return { useType, score: evidence.length, evidence };
  }

  private intendedUseOf(proposal: ProposalDetail): IntendedUse {
    return proposal.intendedUse ?? { useType: proposal.type, description: '' };
  }

  private formatUseType(useType: UseType): string {
    return useType.replaceAll('_', ' ').toLowerCase();
  }

  private assertStaff(): void {
    if (!this.identity.isStaff()) {
      throw this.apiError(403, 'ACCESS_DENIED', 'Triage is restricted to staff members');
    }
  }

  private apiError(status: number, error: string, message: string): never {
    throw { status, error, message };
  }
}
