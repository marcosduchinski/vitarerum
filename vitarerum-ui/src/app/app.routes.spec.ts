import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';
import { of } from 'rxjs';

import { IDENTITY_SERVICE, IdentityService } from '@core/auth/identity.service';
import { IdentitySession } from '@core/auth/models/identity-session.model';
import { AiPromptTemplate, AiPromptVersion } from '@features/ai/prompts/models/ai-prompt.model';
import { AI_PROMPT_MANAGEMENT_SERVICE } from '@features/ai/prompts/services/ai-prompt-management.service';

import { routes } from './app.routes';

const TEMPLATE: AiPromptTemplate = {
  id: 'tpl-1',
  purpose: 'in_situ_narrative',
  key: 'system_institutional',
  name: 'Institutional narrative',
  description: 'Prompt for institutional narratives.',
  variablesSchemaJson: '{"type":"object"}',
  activeVersionId: 'ver-1',
  createdAt: '2026-07-18T10:00:00Z',
};

const VERSION: AiPromptVersion = {
  id: 'ver-1',
  templateId: 'tpl-1',
  version: 1,
  versionLabel: 'museum-narrative-institutional-v1',
  status: 'published',
  content: 'Published prompt.',
  defaultTemperature: 0.3,
  createdBy: 'system',
  createdAt: '2026-07-18T10:00:00Z',
  publishedBy: 'system',
  publishedAt: '2026-07-18T10:00:00Z',
  archivedAt: null,
};

class PromptServiceStub {
  readonly getVersionCalls: string[] = [];

  listTemplates() {
    return of([TEMPLATE]);
  }

  listVersions() {
    return of([VERSION]);
  }

  getVersion(versionId: string) {
    this.getVersionCalls.push(versionId);
    return of(VERSION);
  }

  createDraft() {
    return of(VERSION);
  }

  publishVersion() {
    return of(VERSION);
  }

  archiveVersion() {
    return of(VERSION);
  }

  previewNarrative() {
    return of({});
  }
}

const SESSION: IdentitySession = {
  accessToken: 'token',
  user: {
    id: 'user-1',
    email: 'staff@example.test',
    displayName: 'Staff User',
  },
  group: 'CURATORIAL',
  availableGroups: ['CURATORIAL'],
  permissions: [{ permissionId: 'permission-1', group: 'CURATORIAL' }],
};

const identityStub: IdentityService = {
  session: signal<IdentitySession | null>(SESSION).asReadonly(),
  isAuthenticated: signal(true).asReadonly(),
  isStaff: signal(true).asReadonly(),
  signIn: async () => undefined,
  signOut: () => undefined,
  getAccessToken: () => SESSION.accessToken,
  getPermissionId: () => SESSION.permissions?.[0]?.permissionId ?? null,
  setGroup: () => undefined,
  updateAvailableGroups: () => undefined,
  changePassword: async () => undefined,
  requestPasswordReset: async () => undefined,
  confirmPasswordReset: async () => undefined,
};

describe('app routes', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      providers: [
        provideRouter(routes),
        { provide: IDENTITY_SERVICE, useValue: identityStub },
        { provide: AI_PROMPT_MANAGEMENT_SERVICE, useClass: PromptServiceStub },
      ],
    }).compileComponents();
  });

  it('routes AI prompt version links to the read-only prompt page', async () => {
    const harness = await RouterTestingHarness.create('/p/ai/prompts/versions/ver-1');
    const router = TestBed.inject(Router);
    const promptService = TestBed.inject(
      AI_PROMPT_MANAGEMENT_SERVICE,
    ) as unknown as PromptServiceStub;
    await harness.fixture.whenStable();
    harness.detectChanges();

    expect(router.url).toBe('/p/ai/prompts/versions/ver-1');
    expect(promptService.getVersionCalls).toEqual(['ver-1']);
    expect(harness.routeNativeElement?.textContent).toContain('Displayed version');
    expect(harness.routeNativeElement?.textContent).toContain('Published prompt.');
    expect(harness.routeNativeElement?.textContent).not.toContain('Draft editor');
  });

  it('routes AI prompt edit links to the manage prompt page', async () => {
    const harness = await RouterTestingHarness.create('/p/ai/prompts/tpl-1/edit');
    const router = TestBed.inject(Router);
    await harness.fixture.whenStable();
    harness.detectChanges();

    expect(router.url).toBe('/p/ai/prompts/tpl-1/edit');
    expect(harness.routeNativeElement?.textContent).toContain('Draft editor');
    expect(harness.routeNativeElement?.textContent).toContain('Create draft');
  });
});
