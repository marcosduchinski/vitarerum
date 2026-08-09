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
  AiPromptPurpose,
  AiPromptStatus,
  AiPromptTemplate,
  AiPromptVersion,
} from '../../models/ai-prompt.model';
import { AI_PROMPT_MANAGEMENT_SERVICE } from '../../services/ai-prompt-management.service';

const PURPOSE_OPTIONS: readonly { readonly value: AiPromptPurpose; readonly label: string }[] = [
  { value: 'in_situ_narrative', label: 'Narrative' },
  { value: 'proposal_assistance', label: 'Proposal assistance' },
  { value: 'project_assistance', label: 'Project assistance' },
];

const STATUS_OPTIONS: readonly { readonly value: AiPromptStatus; readonly label: string }[] = [
  { value: 'published', label: 'Published' },
  { value: 'draft', label: 'Draft' },
  { value: 'archived', label: 'Archived' },
];

@Component({
  selector: 'app-ai-prompt-view-page',
  standalone: true,
  imports: [
    DatePipe,
    RouterLink,
    PageHeaderComponent,
    EmptyStateComponent,
    ErrorMessageComponent,
    LoadingStateComponent,
  ],
  templateUrl: './ai-prompt-view-page.component.html',
  styleUrl: './ai-prompt-view-page.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AiPromptViewPageComponent {
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

  protected readonly templates = signal<readonly AiPromptTemplate[]>([]);
  protected readonly versions = signal<readonly AiPromptVersion[]>([]);
  protected readonly readonlyVersion = signal<AiPromptVersion | null>(null);
  protected readonly loadingTemplates = signal(false);
  protected readonly loadingVersions = signal(false);
  protected readonly loadError = signal<ApiError | null>(null);
  protected readonly actionError = signal<ApiError | null>(null);
  protected readonly isReadonlyVersionRoute = computed(() => !!this.selectedVersionId());
  protected readonly canManageTemplate = computed(() => {
    const templateId = this.selectedTemplateId();
    return !this.isReadonlyVersionRoute() && !!templateId?.startsWith('ptpl-');
  });

  protected readonly selectedTemplate = computed(() => {
    const id = this.selectedTemplateId() ?? this.readonlyVersion()?.templateId;
    return this.templates().find((template) => template.id === id) ?? null;
  });
  protected readonly activeVersion = computed(() => {
    const activeId = this.selectedTemplate()?.activeVersionId;
    return this.versions().find((version) => version.id === activeId) ?? null;
  });
  protected readonly displayedVersion = computed(
    () => this.readonlyVersion() ?? this.activeVersion(),
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
      }
    });
  }

  protected statusLabel(status: AiPromptStatus | null | undefined): string {
    return STATUS_OPTIONS.find((option) => option.value === status)?.label ?? 'No versions';
  }

  protected purposeLabel(purpose: AiPromptPurpose): string {
    return PURPOSE_OPTIONS.find((option) => option.value === purpose)?.label ?? purpose;
  }

  protected editLink(template: AiPromptTemplate): readonly string[] {
    return ['/p/ai/prompts', template.id, 'edit'];
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
      this.readonlyVersion.set(version);
      this.versions.set([version]);
    } catch (err) {
      this.actionError.set(toApiError(err));
      this.readonlyVersion.set(null);
      this.versions.set([]);
    } finally {
      this.loadingVersions.set(false);
    }
  }
}
