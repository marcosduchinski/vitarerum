import { UseType } from '@shared/models/collection-use-status.model';

export interface DocumentTemplate {
  readonly id: string;
  readonly useType: UseType;
  readonly title: string;
  readonly description: string;
  readonly mandatory: boolean;
  readonly active: boolean;
  readonly displayOrder: number;
  readonly fileName: string;
  readonly uploadedAt: string;
}

/** Editable metadata sent on PATCH (full replace — the form submits all). */
export interface DocumentTemplateMetadata {
  readonly title: string;
  readonly description: string;
  readonly mandatory: boolean;
  readonly active: boolean;
  readonly displayOrder: number;
}

export interface CreateDocumentTemplateInput extends DocumentTemplateMetadata {
  readonly useType: UseType;
  readonly file: File;
}
