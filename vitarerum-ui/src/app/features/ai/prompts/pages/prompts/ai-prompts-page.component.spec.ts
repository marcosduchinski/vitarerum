import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap, provideRouter } from '@angular/router';
import { BehaviorSubject, of } from 'rxjs';

import {
  AiPromptPreviewInput,
  AiPromptPreviewResult,
  AiPromptTemplate,
  AiPromptTemplateQuery,
  AiPromptVersion,
  CreateAiPromptDraftInput,
} from '../../models/ai-prompt.model';
import { AI_PROMPT_MANAGEMENT_SERVICE } from '../../services/ai-prompt-management.service';
import { AiPromptsPageComponent } from './ai-prompts-page.component';

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

const DRAFT_TEMPLATE: AiPromptTemplate = {
  id: 'tpl-draft',
  purpose: 'proposal_assistance',
  key: 'proposal_summary',
  name: 'Proposal summary',
  description: 'Prompt for proposal summaries.',
  variablesSchemaJson: '{"type":"object"}',
  activeVersionId: null,
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

const DRAFT_VERSION: AiPromptVersion = {
  id: 'ver-draft',
  templateId: 'tpl-draft',
  version: 1,
  versionLabel: 'proposal-summary-v1',
  status: 'draft',
  content: 'Draft prompt.',
  defaultTemperature: 0.3,
  createdBy: 'staff-1',
  createdAt: '2026-07-18T10:15:00Z',
  publishedBy: null,
  publishedAt: null,
  archivedAt: null,
};

class ServiceStub {
  readonly createDraftCalls: [string, CreateAiPromptDraftInput][] = [];
  readonly publishCalls: string[] = [];
  readonly getVersionCalls: string[] = [];
  readonly previewCalls: AiPromptPreviewInput[] = [];
  templates: AiPromptTemplate[] = [TEMPLATE, DRAFT_TEMPLATE];
  versionsByTemplate: Record<string, AiPromptVersion[]> = {
    [TEMPLATE.id]: [VERSION],
    [DRAFT_TEMPLATE.id]: [DRAFT_VERSION],
  };

  listTemplates(query: AiPromptTemplateQuery = {}) {
    return of(
      this.templates.filter((template) => {
        if (query.purpose && template.purpose !== query.purpose) return false;
        if (query.status) {
          const status = (this.versionsByTemplate[template.id] ?? [])
            .slice()
            .sort((a, b) => b.version - a.version)[0]?.status;
          if (status !== query.status) return false;
        }
        return true;
      }),
    );
  }

  listVersions(templateId: string) {
    return of(this.versionsByTemplate[templateId] ?? []);
  }

  getVersion(versionId: string) {
    this.getVersionCalls.push(versionId);
    return of(
      Object.values(this.versionsByTemplate)
        .flat()
        .find((version) => version.id === versionId) ?? VERSION,
    );
  }

  createDraft(templateId: string, input: CreateAiPromptDraftInput) {
    this.createDraftCalls.push([templateId, input]);
    const draft: AiPromptVersion = {
      ...VERSION,
      id: 'ver-2',
      version: 2,
      status: 'draft',
      versionLabel: input.versionLabel,
      content: input.content,
      defaultTemperature: input.defaultTemperature,
      publishedBy: null,
      publishedAt: null,
    };
    this.versionsByTemplate[templateId] = [...(this.versionsByTemplate[templateId] ?? []), draft];
    return of(draft);
  }

  publishVersion(versionId: string) {
    this.publishCalls.push(versionId);
    const published = { ...VERSION, id: versionId, status: 'published' as const };
    this.versionsByTemplate[TEMPLATE.id] = this.versionsByTemplate[TEMPLATE.id].map((version) =>
      version.id === versionId ? published : version,
    );
    return of(published);
  }

  archiveVersion() {
    return of({ ...VERSION, status: 'archived' as const });
  }

  previewNarrative(input: AiPromptPreviewInput) {
    this.previewCalls.push(input);
    const result: AiPromptPreviewResult = {
      recordId: input.recordId,
      status: 'preview',
      generatedAt: '2026-07-18T10:20:00Z',
      narrative: 'Preview narrative text.',
      promptVersionId: input.promptVersionId,
      promptVersion: 'museum-narrative-institutional-v2',
      promptStatus: 'draft',
      llmModel: 'llama3.1:8b',
      creativityTemperature: input.creativityTemperature,
      validationConforms: true,
      modelResponseHash: 'sha256:preview',
    };
    return of(result);
  }
}

describe('AiPromptsPageComponent', () => {
  let fixture: ComponentFixture<AiPromptsPageComponent>;
  let service: ServiceStub;
  let paramMap: BehaviorSubject<ReturnType<typeof convertToParamMap>>;

  beforeEach(async () => {
    service = new ServiceStub();
    paramMap = new BehaviorSubject(convertToParamMap({ templateId: 'tpl-1' }));
    await TestBed.configureTestingModule({
      imports: [AiPromptsPageComponent],
      providers: [
        provideRouter([]),
        { provide: ActivatedRoute, useValue: { paramMap: paramMap.asObservable() } },
        { provide: AI_PROMPT_MANAGEMENT_SERVICE, useValue: service },
      ],
    }).compileComponents();
  });

  it('renders the prompt list and the selected template detail', async () => {
    fixture = TestBed.createComponent(AiPromptsPageComponent);
    await fixture.whenStable();
    fixture.detectChanges();

    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(text).toContain('Institutional narrative');
    expect(text).toContain('museum-narrative-institutional-v1');
    expect(text).toContain('Published prompt.');
    expect(text).toContain('Published by');
    expect(text).toContain('system');
  });

  it('labels a template with only draft versions as draft', async () => {
    fixture = TestBed.createComponent(AiPromptsPageComponent);
    await fixture.whenStable();
    fixture.detectChanges();

    const root = fixture.nativeElement as HTMLElement;
    const purposeSelect = root.querySelector('select');
    if (!(purposeSelect instanceof HTMLSelectElement)) throw new Error('Purpose select not found');
    purposeSelect.value = '';
    purposeSelect.dispatchEvent(new Event('change'));
    await fixture.whenStable();
    fixture.detectChanges();

    const text = root.textContent ?? '';
    expect(text).toContain('Proposal summary');
    expect(text).toContain('Draft');
    expect(text).not.toContain('No versions');
  });

  it('duplicates the active version, edits the draft content, creates and publishes it', async () => {
    fixture = TestBed.createComponent(AiPromptsPageComponent);
    await fixture.whenStable();
    fixture.detectChanges();

    const root = fixture.nativeElement as HTMLElement;
    clickButton(root, 'Duplicate active');
    fixture.detectChanges();

    const textarea = root.querySelector('textarea');
    if (!(textarea instanceof HTMLTextAreaElement)) throw new Error('Draft textarea not found');
    textarea.value = 'Edited prompt content.';
    textarea.dispatchEvent(new Event('input'));
    fixture.detectChanges();

    clickButton(root, 'Create draft');
    await fixture.whenStable();
    fixture.detectChanges();
    clickButton(root, 'Publish');
    await fixture.whenStable();

    expect(service.createDraftCalls[0][0]).toBe('tpl-1');
    expect(service.createDraftCalls[0][1]).toMatchObject({
      versionLabel: 'museum-narrative-institutional-v2',
      content: 'Edited prompt content.',
      defaultTemperature: 0.3,
      sourceVersionId: null,
    });
    expect(service.publishCalls).toEqual(['ver-2']);
  });

  it('renders a prompt version route as read-only exact version content', async () => {
    paramMap.next(convertToParamMap({ versionId: 'ver-1' }));

    fixture = TestBed.createComponent(AiPromptsPageComponent);
    await fixture.whenStable();
    fixture.detectChanges();

    const root = fixture.nativeElement as HTMLElement;
    const text = root.textContent ?? '';

    expect(service.getVersionCalls).toEqual(['ver-1']);
    expect(text).toContain('Displayed version');
    expect(text).toContain('museum-narrative-institutional-v1');
    expect(text).toContain('Published prompt.');
    expect(text).not.toContain('Draft editor');
    expect(buttonWithText(root, 'Duplicate active')).toBeNull();
    expect(buttonWithText(root, 'Duplicate')).toBeNull();
    expect(buttonWithText(root, 'Publish')).toBeNull();
    expect(buttonWithText(root, 'Archive')).toBeNull();
  });

  it('previews a draft narrative prompt with an existing record id', async () => {
    service.versionsByTemplate[TEMPLATE.id] = [
      VERSION,
      {
        ...VERSION,
        id: 'ver-draft',
        version: 2,
        versionLabel: 'museum-narrative-institutional-v2',
        status: 'draft',
        content: 'Draft prompt.',
        defaultTemperature: 0.4,
        publishedBy: null,
        publishedAt: null,
      },
    ];

    fixture = TestBed.createComponent(AiPromptsPageComponent);
    await fixture.whenStable();
    fixture.detectChanges();

    const root = fixture.nativeElement as HTMLElement;
    const recordInput = inputByLabel(root, 'Preview record id');
    recordInput.value = 'record-1';
    recordInput.dispatchEvent(new Event('input'));
    fixture.detectChanges();

    clickButton(root, 'Preview');
    await fixture.whenStable();
    fixture.detectChanges();

    expect(service.previewCalls).toEqual([
      {
        recordId: 'record-1',
        promptVersionId: 'ver-draft',
        narrativeType: 'institutional',
        targetLanguage: 'pt',
        creativityTemperature: 0.4,
      },
    ]);
    const text = root.textContent ?? '';
    expect(text).toContain('Preview narrative text.');
    expect(text).toContain('museum-narrative-institutional-v2');
    expect(text).toContain('llama3.1:8b');
    expect(text).toContain('Temperature 0.4');
  });
});

function clickButton(root: HTMLElement, text: string): void {
  const button = Array.from(root.querySelectorAll('button')).find((candidate) =>
    candidate.textContent?.includes(text),
  );
  if (!(button instanceof HTMLButtonElement)) throw new Error(`Button not found: ${text}`);
  button.click();
}

function buttonWithText(root: HTMLElement, text: string): HTMLButtonElement | null {
  return (
    Array.from(root.querySelectorAll('button')).find((candidate) =>
      candidate.textContent?.includes(text),
    ) ?? null
  );
}

function inputByLabel(root: HTMLElement, label: string): HTMLInputElement {
  const field = Array.from(root.querySelectorAll('label')).find((candidate) =>
    candidate.textContent?.includes(label),
  );
  const input = field?.querySelector('input');
  if (!(input instanceof HTMLInputElement)) throw new Error(`Input not found: ${label}`);
  return input;
}
