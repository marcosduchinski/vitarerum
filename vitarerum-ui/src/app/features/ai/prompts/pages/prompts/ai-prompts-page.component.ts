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
  selector: 'app-ai-prompts-page',
  standalone: true,
  imports: [
    DatePipe,
    RouterLink,
    PageHeaderComponent,
    ErrorMessageComponent,
    LoadingStateComponent,
  ],
  templateUrl: './ai-prompts-page.component.html',
  styleUrl: './ai-prompts-page.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AiPromptsPageComponent {
  private readonly service = inject(AI_PROMPT_MANAGEMENT_SERVICE);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);

  private readonly selectedTemplateId = toSignal(
    this.route.paramMap.pipe(map((params) => params.get('templateId'))),
    { initialValue: null },
  );
  private readonly selectedVersionId = toSignal(
    this.route.paramMap.pipe(map((params) => params.get('versionId'))),
    { initialValue: null },
  );

  protected readonly purposeOptions = PURPOSE_OPTIONS;
  protected readonly statusOptions = STATUS_OPTIONS;
  protected readonly purposeFilter = signal<AiPromptPurpose | null>('in_situ_narrative');
  protected readonly statusFilter = signal<AiPromptStatus | null>(null);

  protected readonly templates = signal<readonly AiPromptTemplate[]>([]);
  protected readonly versions = signal<readonly AiPromptVersion[]>([]);
  protected readonly readonlyVersion = signal<AiPromptVersion | null>(null);
  protected readonly versionsByTemplate = signal<
    Readonly<Record<string, readonly AiPromptVersion[]>>
  >({});
  protected readonly loadingTemplates = signal(false);
  protected readonly loadingVersions = signal(false);
  protected readonly loadError = signal<ApiError | null>(null);
  protected readonly actionError = signal<ApiError | null>(null);
  protected readonly busy = signal(false);
  protected readonly previewingVersionId = signal<string | null>(null);
  protected readonly previewRecordId = signal('');
  protected readonly previewTargetLanguage = signal('pt');
  protected readonly previewResult = signal<AiPromptPreviewResult | null>(null);
  protected readonly isReadonlyVersionRoute = computed(() => !!this.selectedVersionId());

  protected readonly selectedTemplate = computed(() => {
    const id = this.selectedTemplateId() ?? this.readonlyVersion()?.templateId;
    return this.templates().find((template) => template.id === id) ?? null;
  });
  protected readonly activeVersion = computed(() => {
    const activeId = this.selectedTemplate()?.activeVersionId;
    return this.versions().find((version) => version.id === activeId) ?? null;
  });
  protected readonly draftVersions = computed(() =>
    this.versions().filter((version) => version.status === 'draft'),
  );
  protected readonly displayedVersion = computed(
    () => this.readonlyVersion() ?? this.activeVersion(),
  );

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
  protected readonly canPreview = computed(
    () =>
      !this.busy() &&
      !this.previewingVersionId() &&
      !this.isReadonlyVersionRoute() &&
      this.selectedTemplate()?.purpose === 'in_situ_narrative' &&
      !!this.previewRecordId().trim(),
  );

  constructor() {
    void this.loadTemplates();
    effect(() => {
      const versionId = this.selectedVersionId();
      const templateId = this.selectedTemplateId();
      if (versionId) {
        void this.loadReadonlyVersion(versionId);
      } else if (templateId) {
        this.readonlyVersion.set(null);
        void this.loadVersions(templateId);
      } else {
        this.readonlyVersion.set(null);
        this.versions.set([]);
        this.resetDraft();
      }
    });
  }

  protected async setPurposeFilter(event: Event): Promise<void> {
    const value = (event.target as HTMLSelectElement).value;
    this.purposeFilter.set(value ? (value as AiPromptPurpose) : null);
    await this.loadTemplates();
  }

  protected async setStatusFilter(event: Event): Promise<void> {
    const value = (event.target as HTMLSelectElement).value;
    this.statusFilter.set(value ? (value as AiPromptStatus) : null);
    await this.loadTemplates();
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
    return this.latestVersionFor(template)?.status ?? null;
  }

  protected activeVersionFor(template: AiPromptTemplate): AiPromptVersion | null {
    if (!template.activeVersionId) return null;
    return (
      this.versionsFor(template).find((version) => version.id === template.activeVersionId) ?? null
    );
  }

  protected latestVersionFor(template: AiPromptTemplate): AiPromptVersion | null {
    return (
      this.versionsFor(template)
        .slice()
        .sort((a, b) => b.version - a.version)[0] ?? null
    );
  }

  protected lastPublishedFor(template: AiPromptTemplate): AiPromptVersion | null {
    return (
      this.versionsFor(template)
        .filter((version) => version.publishedAt)
        .sort((a, b) => (b.publishedAt ?? '').localeCompare(a.publishedAt ?? ''))[0] ?? null
    );
  }

  protected versionsFor(template: AiPromptTemplate): readonly AiPromptVersion[] {
    return this.versionsByTemplate()[template.id] ?? [];
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
    this.previewingVersionId.set(version.id);
    this.actionError.set(null);
    try {
      this.previewResult.set(
        await firstValueFrom(
          this.service.previewNarrative({
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
      this.previewingVersionId.set(null);
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
      const templates = await firstValueFrom(
        this.service.listTemplates({
          purpose: this.isReadonlyVersionRoute() ? null : this.purposeFilter(),
          status: this.isReadonlyVersionRoute() ? null : this.statusFilter(),
        }),
      );
      this.templates.set(templates);
      await this.loadTemplateVersionSummaries(templates);
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
      this.versionsByTemplate.update((current) => ({
        ...current,
        [templateId]: this.versions(),
      }));
      this.resetDraft();
    } catch (err) {
      this.actionError.set(toApiError(err));
      this.versions.set([]);
    } finally {
      this.loadingVersions.set(false);
    }
  }

  private async loadReadonlyVersion(versionId: string): Promise<void> {
    this.loadingVersions.set(true);
    this.actionError.set(null);
    try {
      const version = await firstValueFrom(this.service.getVersion(versionId));
      this.previewResult.set(null);
      this.readonlyVersion.set(version);
      this.versions.set([version]);
      this.versionsByTemplate.update((current) => ({
        ...current,
        [version.templateId]: [version],
      }));
      this.resetDraft();
    } catch (err) {
      this.actionError.set(toApiError(err));
      this.readonlyVersion.set(null);
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

  private async loadTemplateVersionSummaries(
    templates: readonly AiPromptTemplate[],
  ): Promise<void> {
    const entries = await Promise.all(
      templates.map(
        async (template) =>
          [template.id, await firstValueFrom(this.service.listVersions(template.id))] as const,
      ),
    );
    this.versionsByTemplate.set(Object.fromEntries(entries));
  }
}
