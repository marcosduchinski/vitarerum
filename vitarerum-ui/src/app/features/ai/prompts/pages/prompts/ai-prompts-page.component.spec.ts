import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap, provideRouter, Router } from '@angular/router';
import { MenuItem } from 'primeng/api';
import { BehaviorSubject, of } from 'rxjs';

import {
  CollectionUseProjectSummary,
  ProjectListQuery,
} from '@features/collections/projects/models/project.model';
import { PROJECT_API_SERVICE } from '@features/collections/projects/services/project-api.service';
import { Page } from '@shared/models/page.model';

import {
  AiPromptPreviewInput,
  AiPromptPreviewResult,
  AiPromptTemplate,
  AiPromptTemplateQuery,
  AiPromptVersion,
  CreateAiPromptDraftInput,
} from '../../models/ai-prompt.model';
import { AI_PROMPT_MANAGEMENT_SERVICE } from '../../services/ai-prompt-management.service';
import { AiPromptManagePageComponent } from '../prompt-manage/ai-prompt-manage-page.component';
import { AiPromptViewPageComponent } from '../prompt-view/ai-prompt-view-page.component';
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

const PTPL_TEMPLATE: AiPromptTemplate = {
  ...TEMPLATE,
  id: 'ptpl-insitu-institutional',
  activeVersionId: 'pver-insitu-institutional-v1',
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

const PTPL_VERSION: AiPromptVersion = {
  ...VERSION,
  id: 'pver-insitu-institutional-v1',
  templateId: PTPL_TEMPLATE.id,
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

const COMPLETED_IN_SITU_PROJECT: CollectionUseProjectSummary = {
  id: 'project-closed-1',
  referenceNumber: 'CU-2026-0042',
  title: 'Completed institutional visit',
  purpose: 'Document an in-situ visit.',
  note: null,
  type: 'IN_SITU_VISIT',
  status: 'COMPLETED',
  result: 'COMPLETED',
  beginDate: '2026-07-01',
  endDate: '2026-07-05',
  requestedBy: null,
  proposal: {
    id: 'proposal-closed-1',
    status: 'APPROVED',
    assignedTo: null,
  },
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
      promptVersionId: input.mode === 'version' ? input.promptVersionId : null,
      promptVersion: input.mode === 'version' ? 'museum-narrative-institutional-v2' : null,
      promptStatus: input.mode === 'version' ? 'draft' : null,
      promptSource: input.mode === 'version' ? 'version' : 'adhoc',
      llmModel: 'llama3.1:8b',
      creativityTemperature: input.creativityTemperature,
      validationConforms: true,
      modelResponseHash: 'sha256:preview',
    };
    return of(result);
  }
}

class ProjectServiceStub {
  readonly listProjectsCalls: ProjectListQuery[] = [];
  projects: CollectionUseProjectSummary[] = [COMPLETED_IN_SITU_PROJECT];

  listProjects(query: ProjectListQuery = {}) {
    this.listProjectsCalls.push(query);
    const page: Page<CollectionUseProjectSummary> = {
      content: this.projects,
      page: query.page ?? 0,
      size: query.size ?? this.projects.length,
      totalElements: this.projects.length,
      totalPages: 1,
    };
    return of(page);
  }
}

describe('AiPromptsPageComponent', () => {
  let fixture: ComponentFixture<unknown>;
  let service: ServiceStub;
  let projectService: ProjectServiceStub;
  let paramMap: BehaviorSubject<ReturnType<typeof convertToParamMap>>;

  beforeEach(async () => {
    service = new ServiceStub();
    projectService = new ProjectServiceStub();
    paramMap = new BehaviorSubject(convertToParamMap({ templateId: 'tpl-1' }));
    await TestBed.configureTestingModule({
      imports: [AiPromptsPageComponent, AiPromptViewPageComponent, AiPromptManagePageComponent],
      providers: [
        provideRouter([]),
        { provide: ActivatedRoute, useValue: { paramMap: paramMap.asObservable() } },
        { provide: AI_PROMPT_MANAGEMENT_SERVICE, useValue: service },
        { provide: PROJECT_API_SERVICE, useValue: projectService },
      ],
    }).compileComponents();
  });

  it('renders a simple prompt list on the base route', async () => {
    paramMap.next(convertToParamMap({}));

    fixture = TestBed.createComponent(AiPromptsPageComponent);
    await fixture.whenStable();
    fixture.detectChanges();

    const root = fixture.nativeElement as HTMLElement;
    const text = root.textContent ?? '';
    expect(text).toContain('Institutional narrative');
    expect(text).toContain('Proposal summary');
    expect(text).toContain('Purpose');
    expect(text).toContain('Status');
    expect(text).toContain('Active version');
    expect(text).toContain('Last published');
    expect(text).not.toContain('Variables schema');
    expect(text).not.toContain('Draft editor');
    expect(root.querySelectorAll('app-row-actions').length).toBe(2);
    expect(
      root.querySelector('button[aria-label="More actions for Institutional narrative"]'),
    ).not.toBeNull();
  });

  it('navigates to prompt detail from the row actions menu', async () => {
    paramMap.next(convertToParamMap({}));

    fixture = TestBed.createComponent(AiPromptsPageComponent);
    await fixture.whenStable();

    const router = TestBed.inject(Router);
    const navigate = vi.spyOn(router, 'navigate').mockResolvedValue(true);
    const component = fixture.componentInstance as unknown as {
      actionItemsFor(template: AiPromptTemplate): MenuItem[];
    };

    component.actionItemsFor(TEMPLATE)[0].command?.({ originalEvent: undefined, item: undefined });

    expect(navigate).toHaveBeenCalledWith(['/p/ai/prompts', 'tpl-1']);
  });

  it('renders the selected template detail on a template route', async () => {
    fixture = TestBed.createComponent(AiPromptViewPageComponent);
    await fixture.whenStable();
    fixture.detectChanges();

    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(text).toContain('Institutional narrative');
    expect(text).toContain('museum-narrative-institutional-v1');
    expect(text).toContain('Published prompt.');
    expect(text).toContain('Published by');
    expect(text).toContain('system');
    expect(text).not.toContain('Variables schema');
    expect(text).toContain('Active version');
    expect(text).not.toContain('Displayed version');
    expect(text).not.toContain('Draft editor');
  });

  it('links ptpl template detail routes to the manage screen', async () => {
    paramMap.next(convertToParamMap({ templateId: 'ptpl-insitu-institutional' }));
    service.templates = [...service.templates, PTPL_TEMPLATE];
    service.versionsByTemplate[PTPL_TEMPLATE.id] = [PTPL_VERSION];

    fixture = TestBed.createComponent(AiPromptViewPageComponent);
    await fixture.whenStable();
    fixture.detectChanges();

    const root = fixture.nativeElement as HTMLElement;
    const editLink = Array.from(root.querySelectorAll<HTMLAnchorElement>('a')).find((link) =>
      link.textContent?.includes('Edit'),
    );

    expect(editLink).not.toBeUndefined();
    expect(editLink?.getAttribute('href')).toBe('/p/ai/prompts/ptpl-insitu-institutional/edit');
  });

  it('labels a template with only draft versions as draft', async () => {
    paramMap.next(convertToParamMap({}));

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
    fixture = TestBed.createComponent(AiPromptManagePageComponent);
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
    expect(service.previewCalls).toEqual([]);
    expect(service.publishCalls).toEqual(['ver-2']);
  });

  it('prefills ptpl manage drafts from the active prompt version', async () => {
    paramMap.next(convertToParamMap({ templateId: 'ptpl-insitu-institutional' }));
    service.templates = [...service.templates, PTPL_TEMPLATE];
    service.versionsByTemplate[PTPL_TEMPLATE.id] = [PTPL_VERSION];

    fixture = TestBed.createComponent(AiPromptManagePageComponent);
    await fixture.whenStable();
    fixture.detectChanges();

    const root = fixture.nativeElement as HTMLElement;
    const textarea = root.querySelector('textarea');
    if (!(textarea instanceof HTMLTextAreaElement)) throw new Error('Draft textarea not found');
    const labelInput = inputByLabel(root, 'Version label');

    expect(textarea.value).toBe('Published prompt.');
    expect(labelInput.value).toBe('museum-narrative-institutional-v2');
    expect(service.createDraftCalls).toEqual([]);
  });

  it('renders a prompt version route as read-only exact version content', async () => {
    paramMap.next(convertToParamMap({ versionId: 'ver-1' }));

    fixture = TestBed.createComponent(AiPromptViewPageComponent);
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

    fixture = TestBed.createComponent(AiPromptManagePageComponent);
    await fixture.whenStable();
    fixture.detectChanges();

    const root = fixture.nativeElement as HTMLElement;
    const recordInput = inputByLabel(root, 'Preview record or project id');
    recordInput.value = 'record-1';
    recordInput.dispatchEvent(new Event('input'));
    fixture.detectChanges();

    clickButton(root, 'Preview');
    await fixture.whenStable();
    fixture.detectChanges();

    expect(service.previewCalls).toEqual([
      {
        mode: 'version',
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

  it('tests draft editor content without creating a draft', async () => {
    fixture = TestBed.createComponent(AiPromptManagePageComponent);
    await fixture.whenStable();
    fixture.detectChanges();

    const root = fixture.nativeElement as HTMLElement;
    const recordInput = inputByLabel(root, 'Preview record or project id');
    recordInput.value = 'record-1';
    recordInput.dispatchEvent(new Event('input'));
    const textarea = root.querySelector('textarea');
    if (!(textarea instanceof HTMLTextAreaElement)) throw new Error('Draft textarea not found');
    textarea.value = 'Ad-hoc prompt content.';
    textarea.dispatchEvent(new Event('input'));
    fixture.detectChanges();

    clickButton(root, 'Test');
    await fixture.whenStable();
    fixture.detectChanges();

    expect(service.createDraftCalls).toEqual([]);
    expect(service.previewCalls).toEqual([
      {
        mode: 'adhoc',
        recordId: 'record-1',
        content: 'Ad-hoc prompt content.',
        narrativeType: 'institutional',
        targetLanguage: 'pt',
        creativityTemperature: 0.3,
      },
    ]);
    const text = root.textContent ?? '';
    expect(text).toContain('Preview narrative text.');
    expect(text).toContain('Ad-hoc draft');
  });

  it('shows completed in-situ project references and previews with the project id', async () => {
    fixture = TestBed.createComponent(AiPromptManagePageComponent);
    await fixture.whenStable();
    fixture.detectChanges();

    const root = fixture.nativeElement as HTMLElement;
    const projectSelect = selectByLabel(root, 'Completed in-situ project');
    expect(projectSelect.textContent).toContain('CU-2026-0042 - Completed institutional visit');

    projectSelect.value = 'project-closed-1';
    projectSelect.dispatchEvent(new Event('change'));
    const textarea = root.querySelector('textarea');
    if (!(textarea instanceof HTMLTextAreaElement)) throw new Error('Draft textarea not found');
    textarea.value = 'Ad-hoc prompt content.';
    textarea.dispatchEvent(new Event('input'));
    fixture.detectChanges();

    clickButton(root, 'Test');
    await fixture.whenStable();

    expect(projectService.listProjectsCalls[0]).toMatchObject({
      status: 'COMPLETED',
      type: 'IN_SITU_VISIT',
      page: 0,
      size: 100,
    });
    expect(service.previewCalls.at(-1)).toMatchObject({
      mode: 'adhoc',
      recordId: 'project-closed-1',
    });
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

function selectByLabel(root: HTMLElement, label: string): HTMLSelectElement {
  const field = Array.from(root.querySelectorAll('label')).find((candidate) =>
    candidate.textContent?.includes(label),
  );
  const select = field?.querySelector('select');
  if (!(select instanceof HTMLSelectElement)) throw new Error(`Select not found: ${label}`);
  return select;
}
