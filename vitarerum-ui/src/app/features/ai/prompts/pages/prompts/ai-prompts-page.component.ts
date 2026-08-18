import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { MenuItem } from 'primeng/api';
import { firstValueFrom } from 'rxjs';

import { ApiError, toApiError } from '@core/http/api-error.model';
import { EmptyStateComponent } from '@shared/components/empty-state/empty-state.component';
import { ErrorMessageComponent } from '@shared/components/error-message/error-message.component';
import { LoadingStateComponent } from '@shared/components/loading-state/loading-state.component';
import { PageHeaderComponent } from '@shared/components/page-header/page-header.component';
import { RowActionsComponent } from '@shared/components/row-actions/row-actions.component';

import {
  AI_PROMPT_PURPOSE_OPTIONS,
  aiPromptPurposeLabel,
  AiPromptPurpose,
  AiPromptStatus,
  AiPromptTemplate,
  AiPromptVersion,
} from '../../models/ai-prompt.model';
import { AI_PROMPT_MANAGEMENT_SERVICE } from '../../services/ai-prompt-management.service';

const STATUS_OPTIONS: readonly { readonly value: AiPromptStatus; readonly label: string }[] = [
  { value: 'published', label: 'Published' },
  { value: 'draft', label: 'Draft' },
  { value: 'archived', label: 'Archived' },
];

@Component({
  selector: 'app-ai-prompts-page',
  standalone: true,
  imports: [
    DatePipe,
    RouterLink,
    PageHeaderComponent,
    EmptyStateComponent,
    ErrorMessageComponent,
    LoadingStateComponent,
    RowActionsComponent,
  ],
  templateUrl: './ai-prompts-page.component.html',
  styleUrl: './ai-prompts-page.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AiPromptsPageComponent {
  private readonly service = inject(AI_PROMPT_MANAGEMENT_SERVICE);
  private readonly router = inject(Router);

  protected readonly purposeOptions = AI_PROMPT_PURPOSE_OPTIONS;
  protected readonly statusOptions = STATUS_OPTIONS;
  protected readonly purposeFilter = signal<AiPromptPurpose | null>(null);
  protected readonly statusFilter = signal<AiPromptStatus | null>(null);
  protected readonly templates = signal<readonly AiPromptTemplate[]>([]);
  protected readonly versionsByTemplate = signal<
    Readonly<Record<string, readonly AiPromptVersion[]>>
  >({});
  protected readonly loadingTemplates = signal(false);
  protected readonly loadError = signal<ApiError | null>(null);

  constructor() {
    void this.loadTemplates();
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

  protected readonly purposeLabel = aiPromptPurposeLabel;

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

  protected lastPublishedFor(template: AiPromptTemplate): AiPromptVersion | null {
    return (
      this.versionsFor(template)
        .filter((version) => version.publishedAt)
        .sort((a, b) => (b.publishedAt ?? '').localeCompare(a.publishedAt ?? ''))[0] ?? null
    );
  }

  protected actionItemsFor(template: AiPromptTemplate): MenuItem[] {
    return [
      {
        label: 'Details',
        icon: 'pi pi-eye',
        command: () => {
          void this.router.navigate(['/p/ai/prompts', template.id]);
        },
      },
      {
        label: 'Edit',
        icon: 'pi pi-pencil',
        command: () => {
          void this.router.navigate(['/p/ai/prompts', template.id, 'edit']);
        },
      },
    ];
  }

  protected async loadTemplates(): Promise<void> {
    this.loadingTemplates.set(true);
    this.loadError.set(null);
    try {
      const templates = await firstValueFrom(
        this.service.listTemplates({
          purpose: this.purposeFilter(),
          status: this.statusFilter(),
        }),
      );
      this.templates.set(templates);
      await this.loadTemplateVersionSummaries(templates);
    } catch (err) {
      this.loadError.set(toApiError(err));
    } finally {
      this.loadingTemplates.set(false);
    }
  }

  private latestVersionFor(template: AiPromptTemplate): AiPromptVersion | null {
    return (
      this.versionsFor(template)
        .slice()
        .sort((a, b) => b.version - a.version)[0] ?? null
    );
  }

  private versionsFor(template: AiPromptTemplate): readonly AiPromptVersion[] {
    return this.versionsByTemplate()[template.id] ?? [];
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
