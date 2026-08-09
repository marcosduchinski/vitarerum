export type AiPromptPurpose = 'in_situ_narrative' | 'proposal_assistance' | 'project_assistance';

export type AiPromptStatus = 'draft' | 'published' | 'archived';

export interface AiPromptTemplate {
  readonly id: string;
  readonly purpose: AiPromptPurpose;
  readonly key: string;
  readonly name: string;
  readonly description: string;
  readonly variablesSchemaJson: string;
  readonly activeVersionId: string | null;
  readonly createdAt: string;
}

export interface AiPromptVersion {
  readonly id: string;
  readonly templateId: string;
  readonly version: number;
  readonly versionLabel: string;
  readonly status: AiPromptStatus;
  readonly content: string;
  readonly defaultTemperature: number;
  readonly createdBy: string;
  readonly createdAt: string;
  readonly publishedBy: string | null;
  readonly publishedAt: string | null;
  readonly archivedAt: string | null;
}

export interface CreateAiPromptDraftInput {
  readonly versionLabel: string;
  readonly content: string;
  readonly defaultTemperature: number;
  readonly sourceVersionId?: string | null;
}

export interface AiPromptTemplateQuery {
  readonly purpose?: AiPromptPurpose | null;
  readonly status?: AiPromptStatus | null;
}

export type AiPromptPreviewInput =
  | {
      readonly mode: 'version';
      readonly recordId: string;
      readonly promptVersionId: string;
      readonly narrativeType?: string | null;
      readonly targetLanguage: string;
      readonly creativityTemperature: number;
    }
  | {
      readonly mode: 'adhoc';
      readonly recordId: string;
      readonly content: string;
      readonly narrativeType: string;
      readonly targetLanguage: string;
      readonly creativityTemperature: number;
    };

export interface AiPromptPreviewResult {
  readonly recordId: string;
  readonly status: 'preview';
  readonly generatedAt: string;
  readonly narrative: string;
  readonly promptVersionId: string | null;
  readonly promptVersion: string | null;
  readonly promptStatus: AiPromptStatus | null;
  readonly promptSource: 'version' | 'adhoc';
  readonly llmModel: string;
  readonly creativityTemperature: number;
  readonly validationConforms: boolean;
  readonly modelResponseHash: string;
}
