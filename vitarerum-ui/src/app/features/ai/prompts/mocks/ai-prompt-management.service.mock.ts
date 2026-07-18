import { Injectable } from '@angular/core';
import { Observable, of, throwError } from 'rxjs';

import {
  AiPromptPreviewInput,
  AiPromptPreviewResult,
  AiPromptStatus,
  AiPromptTemplate,
  AiPromptTemplateQuery,
  AiPromptVersion,
  CreateAiPromptDraftInput,
} from '../models/ai-prompt.model';
import { AiPromptManagementApi } from '../services/ai-prompt-management.service';

const NOW = '2026-07-18T10:00:00Z';

@Injectable()
export class AiPromptManagementServiceMock implements AiPromptManagementApi {
  private readonly templates: AiPromptTemplate[] = [
    template('tpl-institutional', 'system_institutional', 'Institutional narrative', 'v1'),
    template('tpl-scientific', 'system_scientific', 'Scientific narrative', 'v1'),
    template('tpl-adult', 'system_audioguide_adult', 'Audioguide adult narrative', 'v1'),
    template('tpl-child', 'system_audioguide_child', 'Audioguide child narrative', 'v1'),
    template('tpl-social', 'system_social_media', 'Social media narrative', 'v1'),
  ];

  private readonly versions: AiPromptVersion[] = this.templates.map((item) =>
    version({
      id: item.activeVersionId ?? `${item.id}-v1`,
      templateId: item.id,
      versionNumber: 1,
      label: labelFor(item.key, 1),
      status: 'published',
      content: `Published prompt for ${item.name.toLowerCase()}.`,
    }),
  );

  listTemplates(query: AiPromptTemplateQuery = {}): Observable<AiPromptTemplate[]> {
    return of(
      this.templates.filter((template) => {
        if (query.purpose && template.purpose !== query.purpose) return false;
        if (query.status) {
          const current = this.currentStatus(template);
          if (current !== query.status) return false;
        }
        return true;
      }),
    );
  }

  listVersions(templateId: string): Observable<AiPromptVersion[]> {
    return of(
      this.versions
        .filter((version) => version.templateId === templateId)
        .sort((a, b) => a.version - b.version),
    );
  }

  getVersion(versionId: string): Observable<AiPromptVersion> {
    const found = this.versions.find((version) => version.id === versionId);
    return found ? of(found) : throwError(() => new Error('Prompt version not found'));
  }

  createDraft(templateId: string, input: CreateAiPromptDraftInput): Observable<AiPromptVersion> {
    const existing = this.versions.filter((version) => version.templateId === templateId);
    const next = existing.reduce((max, item) => Math.max(max, item.version), 0) + 1;
    const draft = version({
      id: `${templateId}-v${next}`,
      templateId,
      versionNumber: next,
      label: input.versionLabel,
      status: 'draft',
      content: input.content,
      defaultTemperature: input.defaultTemperature,
    });
    this.versions.push(draft);
    return of(draft);
  }

  publishVersion(versionId: string): Observable<AiPromptVersion> {
    const target = this.versions.find((version) => version.id === versionId);
    if (!target || target.status !== 'draft') return throwError(() => new Error('Invalid draft'));
    for (const version of this.versions) {
      if (version.templateId === target.templateId && version.status === 'published') {
        replace(this.versions, version, { ...version, status: 'archived', archivedAt: NOW });
      }
    }
    const published = {
      ...target,
      status: 'published' as const,
      publishedAt: NOW,
      publishedBy: 'mock',
    };
    replace(this.versions, target, published);
    const template = this.templates.find((item) => item.id === target.templateId);
    if (template) replace(this.templates, template, { ...template, activeVersionId: published.id });
    return of(published);
  }

  archiveVersion(versionId: string): Observable<AiPromptVersion> {
    const target = this.versions.find((version) => version.id === versionId);
    if (!target || target.status === 'published')
      return throwError(() => new Error('Invalid archive'));
    const archived = { ...target, status: 'archived' as const, archivedAt: NOW };
    replace(this.versions, target, archived);
    return of(archived);
  }

  previewNarrative(input: AiPromptPreviewInput): Observable<AiPromptPreviewResult> {
    const version = this.versions.find((item) => item.id === input.promptVersionId);
    if (!version) return throwError(() => new Error('Prompt version not found'));
    return of({
      recordId: input.recordId,
      status: 'preview',
      generatedAt: NOW,
      narrative: `Preview narrative for ${input.recordId} using ${version.versionLabel}.`,
      promptVersionId: version.id,
      promptVersion: version.versionLabel,
      promptStatus: version.status,
      llmModel: 'mock-narrative-model',
      creativityTemperature: input.creativityTemperature,
      validationConforms: true,
      modelResponseHash: 'mock-preview-hash',
    });
  }

  private currentStatus(template: AiPromptTemplate): AiPromptStatus | null {
    const active = this.versions.find((version) => version.id === template.activeVersionId);
    if (active) return active.status;
    const latest = this.versions
      .filter((version) => version.templateId === template.id)
      .sort((a, b) => b.version - a.version)[0];
    return latest?.status ?? null;
  }
}

function template(id: string, key: string, name: string, suffix: string): AiPromptTemplate {
  return {
    id,
    purpose: 'in_situ_narrative',
    key,
    name,
    description: `Prompt template for ${name.toLowerCase()}.`,
    variablesSchemaJson: '{"type":"object"}',
    activeVersionId: `${id}-${suffix}`,
    createdAt: NOW,
  };
}

function version(input: {
  id: string;
  templateId: string;
  versionNumber: number;
  label: string;
  status: AiPromptStatus;
  content: string;
  defaultTemperature?: number;
}): AiPromptVersion {
  return {
    id: input.id,
    templateId: input.templateId,
    version: input.versionNumber,
    versionLabel: input.label,
    status: input.status,
    content: input.content,
    defaultTemperature: input.defaultTemperature ?? 0.3,
    createdBy: 'system',
    createdAt: NOW,
    publishedBy: input.status === 'published' ? 'system' : null,
    publishedAt: input.status === 'published' ? NOW : null,
    archivedAt: input.status === 'archived' ? NOW : null,
  };
}

function labelFor(key: string, versionNumber: number): string {
  return `museum-narrative-${key.replace('system_', '').replaceAll('_', '-')}-v${versionNumber}`;
}

function replace<T>(items: T[], current: T, next: T): void {
  const index = items.indexOf(current);
  if (index >= 0) items[index] = next;
}
