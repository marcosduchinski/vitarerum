import { Routes } from '@angular/router';

export const AI_PROMPTS_ROUTES: Routes = [
  {
    path: '',
    title: 'AI prompts',
    loadComponent: () =>
      import('./pages/prompts/ai-prompts-page.component').then((m) => m.AiPromptsPageComponent),
  },
  {
    path: 'versions/:versionId',
    title: 'AI prompt version',
    loadComponent: () =>
      import('./pages/prompt-view/ai-prompt-view-page.component').then(
        (m) => m.AiPromptViewPageComponent,
      ),
  },
  {
    path: ':templateId/edit',
    title: 'Manage AI prompt',
    loadComponent: () =>
      import('./pages/prompt-manage/ai-prompt-manage-page.component').then(
        (m) => m.AiPromptManagePageComponent,
      ),
  },
  {
    path: ':templateId',
    title: 'AI prompts',
    loadComponent: () =>
      import('./pages/prompt-view/ai-prompt-view-page.component').then(
        (m) => m.AiPromptViewPageComponent,
      ),
  },
];
