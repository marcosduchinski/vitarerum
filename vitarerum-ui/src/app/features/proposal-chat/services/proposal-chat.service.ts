import { HttpClient } from '@angular/common/http';
import { inject, Injectable, InjectionToken } from '@angular/core';
import { API_BASE_URL } from '@core/config/app-config.model';
import { buildApiUrl } from '@core/http/api-url.util';
import { buildHttpParams } from '@core/http/http-params.util';
import { map, Observable } from 'rxjs';

import {
  IntendedUseSuggestion,
  IntendedUseSuggestionResponse,
  ProposalChatContext,
  ProposalChatContextQuery,
  SuggestIntendedUseRequest,
} from '../models/proposal-chat.model';

export const PROPOSAL_CHAT_SERVICE = new InjectionToken<ProposalChatService>(
  'PROPOSAL_CHAT_SERVICE',
);

@Injectable()
export class ProposalChatService {
  private readonly http = inject(HttpClient);
  private readonly apiBaseUrl = inject(API_BASE_URL);

  getContext(query: ProposalChatContextQuery): Observable<ProposalChatContext> {
    return this.http.get<ProposalChatContext>(this.url('/proposalchat/context'), {
      params: buildHttpParams(query),
    });
  }

  suggestIntendedUse(request: SuggestIntendedUseRequest): Observable<IntendedUseSuggestion> {
    return this.http
      .post<IntendedUseSuggestionResponse>(
        this.url('/proposalchat/intended-use-suggestions'),
        request,
      )
      .pipe(map((response) => response.suggestion));
  }

  private url(path: string): string {
    return buildApiUrl(this.apiBaseUrl, path);
  }
}
