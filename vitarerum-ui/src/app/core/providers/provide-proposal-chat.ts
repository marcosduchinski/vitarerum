import { inject, Provider } from '@angular/core';
import { USE_MOCK_API } from '@core/config/app-config.model';
import { ProposalChatServiceMock } from '@features/proposal-chat/mocks/proposal-chat.service.mock';
import {
  PROPOSAL_CHAT_SERVICE,
  ProposalChatService,
} from '@features/proposal-chat/services/proposal-chat.service';

export function provideProposalChat(): Provider[] {
  return [
    ProposalChatService,
    ProposalChatServiceMock,
    {
      provide: PROPOSAL_CHAT_SERVICE,
      useFactory: () =>
        inject(USE_MOCK_API) ? inject(ProposalChatServiceMock) : inject(ProposalChatService),
    },
  ];
}
