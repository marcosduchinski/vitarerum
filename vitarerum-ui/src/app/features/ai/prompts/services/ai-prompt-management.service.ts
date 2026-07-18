import { HttpClient } from '@angular/common/http';
import { inject, Injectable, InjectionToken } from '@angular/core';
import { API_BASE_URL } from '@core/config/app-config.model';
import { buildApiUrl } from '@core/http/api-url.util';
import { buildHttpParams } from '@core/http/http-params.util';
import { map, Observable } from 'rxjs';

import {
  AiPromptPreviewInput,
  AiPromptPreviewResult,
  AiPromptTemplate,
  AiPromptTemplateQuery,
  AiPromptVersion,
  CreateAiPromptDraftInput,
} from '../models/ai-prompt.model';

export interface AiPromptManagementApi {
  listTemplates(query?: AiPromptTemplateQuery): Observable<AiPromptTemplate[]>;
  listVersions(templateId: string): Observable<AiPromptVersion[]>;
  getVersion(versionId: string): Observable<AiPromptVersion>;
  createDraft(templateId: string, input: CreateAiPromptDraftInput): Observable<AiPromptVersion>;
  publishVersion(versionId: string): Observable<AiPromptVersion>;
  archiveVersion(versionId: string): Observable<AiPromptVersion>;
  previewNarrative(input: AiPromptPreviewInput): Observable<AiPromptPreviewResult>;
}

export const AI_PROMPT_MANAGEMENT_SERVICE = new InjectionToken<AiPromptManagementApi>(
  'AI_PROMPT_MANAGEMENT_SERVICE',
);

@Injectable()
export class AiPromptManagementService implements AiPromptManagementApi {
  private readonly http = inject(HttpClient);
  private readonly apiBaseUrl = inject(API_BASE_URL);

  listTemplates(query: AiPromptTemplateQuery = {}): Observable<AiPromptTemplate[]> {
    return this.http.get<AiPromptTemplate[]>(this.url('/ai/prompts'), {
      params: buildHttpParams({
        purpose: query.purpose ?? undefined,
        status: query.status ?? undefined,
      }),
    });
  }

  listVersions(templateId: string): Observable<AiPromptVersion[]> {
    return this.http.get<AiPromptVersion[]>(this.url(`/ai/prompts/${templateId}/versions`));
  }

  getVersion(versionId: string): Observable<AiPromptVersion> {
    return this.http.get<AiPromptVersion>(this.url(`/ai/prompts/versions/${versionId}`));
  }

  createDraft(templateId: string, input: CreateAiPromptDraftInput): Observable<AiPromptVersion> {
    return this.http.post<AiPromptVersion>(this.url(`/ai/prompts/${templateId}/versions`), {
      version_label: input.versionLabel,
      content: input.content,
      default_temperature: input.defaultTemperature,
      source_version_id: input.sourceVersionId ?? null,
    });
  }

  publishVersion(versionId: string): Observable<AiPromptVersion> {
    return this.http.post<AiPromptVersion>(
      this.url(`/ai/prompts/versions/${versionId}/publish`),
      {},
    );
  }

  archiveVersion(versionId: string): Observable<AiPromptVersion> {
    return this.http.post<AiPromptVersion>(
      this.url(`/ai/prompts/versions/${versionId}/archive`),
      {},
    );
  }

  previewNarrative(input: AiPromptPreviewInput): Observable<AiPromptPreviewResult> {
    return this.http
      .post<AiPromptPreviewResponse>(
        this.url(`/cidoc-mapping/in-situ-visit/${input.recordId}/narrative/preview`),
        {
          prompt_version_id: input.promptVersionId,
          narrative_type: input.narrativeType ?? null,
          target_language: input.targetLanguage,
          creativity_temperature: input.creativityTemperature,
        },
      )
      .pipe(mapPreviewResponse);
  }

  private url(path: string): string {
    return buildApiUrl(this.apiBaseUrl, path);
  }
}

interface AiPromptPreviewResponse {
  readonly record_id: string;
  readonly status: 'preview';
  readonly generated_at: string;
  readonly data: { readonly narrative: string };
  readonly meta: {
    readonly prompt_version_id: string;
    readonly prompt_version: string;
    readonly prompt_status: AiPromptPreviewResult['promptStatus'];
    readonly llm_model: string;
    readonly creativity_temperature: number;
    readonly validation_conforms: boolean;
    readonly model_response_hash: string;
  };
}

function mapPreviewResponse(
  source: Observable<AiPromptPreviewResponse>,
): Observable<AiPromptPreviewResult> {
  return source.pipe(
    map((response) => ({
      recordId: response.record_id,
      status: response.status,
      generatedAt: response.generated_at,
      narrative: response.data.narrative,
      promptVersionId: response.meta.prompt_version_id,
      promptVersion: response.meta.prompt_version,
      promptStatus: response.meta.prompt_status,
      llmModel: response.meta.llm_model,
      creativityTemperature: response.meta.creativity_temperature,
      validationConforms: response.meta.validation_conforms,
      modelResponseHash: response.meta.model_response_hash,
    })),
  );
}
