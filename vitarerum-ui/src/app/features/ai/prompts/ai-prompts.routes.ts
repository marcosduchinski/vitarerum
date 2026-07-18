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
      import('./pages/prompts/ai-prompts-page.component').then((m) => m.AiPromptsPageComponent),
  },
  {
    path: ':templateId',
    title: 'AI prompts',
    loadComponent: () =>
      import('./pages/prompts/ai-prompts-page.component').then((m) => m.AiPromptsPageComponent),
  },
];
