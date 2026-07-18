import { inject, Provider } from '@angular/core';
import { USE_MOCK_API } from '@core/config/app-config.model';
import { AiPromptManagementServiceMock } from '@features/ai/prompts/mocks/ai-prompt-management.service.mock';
import {
  AI_PROMPT_MANAGEMENT_SERVICE,
  AiPromptManagementService,
} from '@features/ai/prompts/services/ai-prompt-management.service';

export function provideAiPrompts(): Provider[] {
  return [
    AiPromptManagementService,
    AiPromptManagementServiceMock,
    {
      provide: AI_PROMPT_MANAGEMENT_SERVICE,
      useFactory: () =>
        inject(USE_MOCK_API)
          ? inject(AiPromptManagementServiceMock)
          : inject(AiPromptManagementService),
    },
  ];
}
