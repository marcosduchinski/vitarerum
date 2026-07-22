import { DatePipe } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  effect,
  inject,
  signal,
} from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { firstValueFrom, map } from 'rxjs';

import { ApiError, toApiError } from '@core/http/api-error.model';
import { EmptyStateComponent } from '@shared/components/empty-state/empty-state.component';
import { ErrorMessageComponent } from '@shared/components/error-message/error-message.component';
import { LoadingStateComponent } from '@shared/components/loading-state/loading-state.component';
import { PageHeaderComponent } from '@shared/components/page-header/page-header.component';

import {
  AiPromptPreviewResult,
  AiPromptPurpose,
  AiPromptStatus,
  AiPromptTemplate,
  AiPromptVersion,
} from '../../models/ai-prompt.model';
import { AI_PROMPT_MANAGEMENT_SERVICE } from '../../services/ai-prompt-management.service';

const PURPOSE_OPTIONS: readonly { readonly value: AiPromptPurpose; readonly label: string }[] = [
  { value: 'in_situ_narrative', label: 'Narrative' },
  { value: 'museum_question_triage', label: 'Museum question triage' },
  { value: 'proposal_assistance', label: 'Proposal assistance' },
  { value: 'project_assistance', label: 'Project assistance' },
];

const STATUS_OPTIONS: readonly { readonly value: AiPromptStatus; readonly label: string }[] = [
  { value: 'published', label: 'Published' },
  { value: 'draft', label: 'Draft' },
  { value: 'archived', label: 'Archived' },
];

const NARRATIVE_TYPE_BY_TEMPLATE_KEY: Readonly<Record<string, string>> = {
  system_institutional: 'institutional',
  system_scientific: 'scientific',
  system_audioguide_adult: 'audioguide_adult',
  system_audioguide_child: 'audioguide_child',
  system_social_media: 'social_media',
};

@Component({
  selector: 'app-ai-prompt-manage-page',
  standalone: true,
  imports: [
    DatePipe,
    RouterLink,
    PageHeaderComponent,
    EmptyStateComponent,
    ErrorMessageComponent,
    LoadingStateComponent,
  ],
  templateUrl: './ai-prompt-manage-page.component.html',
  styleUrl: './ai-prompt-manage-page.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AiPromptManagePageComponent {
  private readonly service = inject(AI_PROMPT_MANAGEMENT_SERVICE);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);

  private readonly selectedTemplateId = toSignal(
    this.route.paramMap.pipe(map((params) => params.get('templateId'))),
    { initialValue: null },
  );

  protected readonly templates = signal<readonly AiPromptTemplate[]>([]);
  protected readonly versions = signal<readonly AiPromptVersion[]>([]);
  protected readonly loadingTemplates = signal(false);
  protected readonly loadingVersions = signal(false);
  protected readonly loadError = signal<ApiError | null>(null);
  protected readonly actionError = signal<ApiError | null>(null);
  protected readonly busy = signal(false);
  protected readonly previewingTarget = signal<'draft' | string | null>(null);
  protected readonly previewRecordId = signal('');
  protected readonly previewTargetLanguage = signal('pt');
  protected readonly previewResult = signal<AiPromptPreviewResult | null>(null);

  protected readonly selectedTemplate = computed(() => {
    const id = this.selectedTemplateId();
    return this.templates().find((template) => template.id === id) ?? null;
  });
  protected readonly activeVersion = computed(() => {
    const activeId = this.selectedTemplate()?.activeVersionId;
    return this.versions().find((version) => version.id === activeId) ?? null;
  });
  protected readonly displayedVersion = computed(() => this.activeVersion());

  protected readonly draftVersionLabel = signal('');
  protected readonly draftContent = signal('');
  protected readonly draftTemperature = signal(0.3);
  protected readonly draftSourceId = signal<string | null>(null);

  protected readonly canCreateDraft = computed(
    () =>
      !this.busy() &&
      !!this.selectedTemplate() &&
      !!this.draftVersionLabel().trim() &&
      !!this.draftContent().trim(),
  );
  protected readonly canPreview = computed(() => {
    const template = this.selectedTemplate();
    if (!template) return false;
    return (
      !this.busy() &&
      this.previewingTarget() === null &&
      template.purpose === 'in_situ_narrative' &&
      !!this.previewRecordId().trim() &&
      !!NARRATIVE_TYPE_BY_TEMPLATE_KEY[template.key]
    );
  });
  protected readonly canTestDraft = computed(() => {
    const template = this.selectedTemplate();
    if (!template) return false;
    return (
      !this.busy() &&
      this.previewingTarget() === null &&
      template.purpose === 'in_situ_narrative' &&
      !!this.draftContent().trim() &&
      !!this.previewRecordId().trim() &&
      !!NARRATIVE_TYPE_BY_TEMPLATE_KEY[template.key]
    );
  });

  constructor() {
    void this.loadTemplates();
    effect(() => {
      const templateId = this.selectedTemplateId();
      if (templateId) {
        void this.loadVersions(templateId);
      } else {
        this.versions.set([]);
        this.resetDraft();
      }
    });
  }

  protected statusLabel(status: AiPromptStatus | null | undefined): string {
    return STATUS_OPTIONS.find((option) => option.value === status)?.label ?? 'No versions';
  }

  protected purposeLabel(purpose: AiPromptPurpose): string {
    return PURPOSE_OPTIONS.find((option) => option.value === purpose)?.label ?? purpose;
  }

  protected currentStatus(template: AiPromptTemplate): AiPromptStatus | null {
    const active = this.activeVersionFor(template);
    if (active) return active.status;
    return this.latestVersionFor()?.status ?? null;
  }

  protected activeVersionFor(template: AiPromptTemplate): AiPromptVersion | null {
    if (!template.activeVersionId) return null;
    return this.versions().find((version) => version.id === template.activeVersionId) ?? null;
  }

  protected latestVersionFor(): AiPromptVersion | null {
    return (
      this.versions()
        .slice()
        .sort((a, b) => b.version - a.version)[0] ?? null
    );
  }

  protected viewDetails(template: AiPromptTemplate): void {
    void this.router.navigate(['/p/ai/prompts', template.id]);
  }

  protected duplicateVersion(version: AiPromptVersion): void {
    this.draftSourceId.set(version.id);
    this.draftVersionLabel.set(this.nextVersionLabel(version));
    this.draftContent.set(version.content);
    this.draftTemperature.set(version.defaultTemperature);
  }

  protected async createDraft(): Promise<void> {
    const template = this.selectedTemplate();
    if (!template || !this.canCreateDraft()) return;
    await this.run(async () => {
      await firstValueFrom(
        this.service.createDraft(template.id, {
          versionLabel: this.draftVersionLabel().trim(),
          content: this.draftContent().trim(),
          defaultTemperature: this.draftTemperature(),
          sourceVersionId: null,
        }),
      );
      this.resetDraft();
      await this.loadVersions(template.id);
    });
  }

  protected async publish(version: AiPromptVersion): Promise<void> {
    await this.run(async () => {
      await firstValueFrom(this.service.publishVersion(version.id));
      await this.loadTemplates();
      await this.loadVersions(version.templateId);
    });
  }

  protected async archive(version: AiPromptVersion): Promise<void> {
    await this.run(async () => {
      await firstValueFrom(this.service.archiveVersion(version.id));
      await this.loadTemplates();
      await this.loadVersions(version.templateId);
    });
  }

  protected async preview(version: AiPromptVersion): Promise<void> {
    const template = this.selectedTemplate();
    if (!template || !this.canPreview()) return;
    const narrativeType = NARRATIVE_TYPE_BY_TEMPLATE_KEY[template.key] ?? null;
    this.previewingTarget.set(version.id);
    this.actionError.set(null);
    try {
      this.previewResult.set(
        await firstValueFrom(
          this.service.previewNarrative({
            mode: 'version',
            recordId: this.previewRecordId().trim(),
            promptVersionId: version.id,
            narrativeType,
            targetLanguage: this.previewTargetLanguage().trim() || 'pt',
            creativityTemperature: version.defaultTemperature,
          }),
        ),
      );
    } catch (err) {
      this.actionError.set(toApiError(err));
      this.previewResult.set(null);
    } finally {
      this.previewingTarget.set(null);
    }
  }

  protected async testDraft(): Promise<void> {
    const template = this.selectedTemplate();
    const narrativeType = template ? NARRATIVE_TYPE_BY_TEMPLATE_KEY[template.key] : null;
    if (!template || !narrativeType || !this.canTestDraft()) return;
    this.previewingTarget.set('draft');
    this.actionError.set(null);
    try {
      this.previewResult.set(
        await firstValueFrom(
          this.service.previewNarrative({
            mode: 'adhoc',
            recordId: this.previewRecordId().trim(),
            content: this.draftContent().trim(),
            narrativeType,
            targetLanguage: this.previewTargetLanguage().trim() || 'pt',
            creativityTemperature: this.draftTemperature(),
          }),
        ),
      );
    } catch (err) {
      this.actionError.set(toApiError(err));
      this.previewResult.set(null);
    } finally {
      this.previewingTarget.set(null);
    }
  }

  protected resetDraft(): void {
    this.draftVersionLabel.set('');
    this.draftContent.set('');
    this.draftTemperature.set(0.3);
    this.draftSourceId.set(null);
  }

  protected async loadTemplates(): Promise<void> {
    this.loadingTemplates.set(true);
    this.loadError.set(null);
    try {
      const templates = await firstValueFrom(this.service.listTemplates());
      this.templates.set(templates);
      const selected = this.selectedTemplateId();
      if (selected && !templates.some((template) => template.id === selected)) {
        await this.router.navigate(['/p/ai/prompts']);
      }
    } catch (err) {
      this.loadError.set(toApiError(err));
    } finally {
      this.loadingTemplates.set(false);
    }
  }

  private async loadVersions(templateId: string): Promise<void> {
    this.loadingVersions.set(true);
    this.actionError.set(null);
    try {
      this.versions.set(await firstValueFrom(this.service.listVersions(templateId)));
      this.previewResult.set(null);
      this.resetDraft();
    } catch (err) {
      this.actionError.set(toApiError(err));
      this.versions.set([]);
    } finally {
      this.loadingVersions.set(false);
    }
  }

  private async run(operation: () => Promise<void>): Promise<void> {
    this.busy.set(true);
    this.actionError.set(null);
    try {
      await operation();
    } catch (err) {
      this.actionError.set(toApiError(err));
    } finally {
      this.busy.set(false);
    }
  }

  private nextVersionLabel(version: AiPromptVersion): string {
    const base = version.versionLabel.replace(/-v\d+$/, '');
    const next = Math.max(...this.versions().map((item) => item.version), version.version) + 1;
    return `${base}-v${next}`;
  }
}
