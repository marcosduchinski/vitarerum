export type ReferenceKind =
  | 'PROPOSAL'
  | 'COLLECTION_USE_PROJECT'
  | 'OBJECT_ACCESS_LOG'
  | 'OBJECT_OCCURRENCE_LOG'
  | 'PUBLICATION_LOG';

export type ReferencePolicyStatus = 'DRAFT' | 'ACTIVE' | 'INACTIVE' | 'RETIRED';

export type ReferenceSequenceScope = 'GLOBAL' | 'YEAR' | 'MONTH' | 'DAY';

export interface ReferencePolicy {
  readonly id: string;
  readonly kind: ReferenceKind;
  readonly mask: string;
  readonly sequenceScope: ReferenceSequenceScope;
  readonly status: ReferencePolicyStatus;
  readonly activeFrom: string | null;
  readonly activeUntil: string | null;
  readonly createdBy: string;
  readonly createdAt: string;
  readonly updatedBy: string | null;
  readonly updatedAt: string | null;
  readonly activatedBy: string | null;
  readonly activatedAt: string | null;
}

export interface ReferencePolicyPreview {
  readonly kind: ReferenceKind;
  readonly mask: string;
  readonly sequenceScope: ReferenceSequenceScope;
  readonly example: string;
  readonly tokens: readonly string[];
}

export interface CreateReferencePolicyInput {
  readonly kind: ReferenceKind;
  readonly mask: string;
}

export interface PreviewReferencePolicyInput extends CreateReferencePolicyInput {
  readonly sampleDate: string;
}
