export type AiPromptPurpose =
  | 'in_situ_narrative'
  | 'proposal_assistance'
  | 'project_assistance'
  | 'scientific_return_analysis';

/**
 * Purposes offered in the interface, in display order.
 *
 * Narrower than the type on purpose: `proposal_assistance` and
 * `project_assistance` exist in the backend enum but no prompt has ever used
 * them. The type still carries them so a template that arrives with one is
 * typed honestly and falls back to its raw value in the label.
 */
export const AI_PROMPT_PURPOSE_OPTIONS: readonly {
  readonly value: AiPromptPurpose;
  readonly label: string;
}[] = [
  { value: 'in_situ_narrative', label: 'Narrative' },
  { value: 'scientific_return_analysis', label: 'Scientific Return' },
];

export function aiPromptPurposeLabel(purpose: AiPromptPurpose): string {
  return AI_PROMPT_PURPOSE_OPTIONS.find((option) => option.value === purpose)?.label ?? purpose;
}

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
