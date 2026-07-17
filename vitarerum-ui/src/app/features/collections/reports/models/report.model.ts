import { Page, PageQuery } from '@shared/models/page.model';

export type InSituVisitReportTargetLanguage = 'pt' | 'en';
export type InSituVisitReportNarrativeType =
  | 'institutional'
  | 'scientific'
  | 'audioguide_adult'
  | 'audioguide_child'
  | 'social_media';

export interface CreateInSituVisitReportRequest {
  readonly targetLanguage: InSituVisitReportTargetLanguage;
  readonly narrativeType: InSituVisitReportNarrativeType;
  readonly creativityTemperature: number;
}

export interface UpdateInSituVisitNarrativeRequest {
  readonly narrative: string;
}

export type CidocCrmJsonPrimitive = string | number | boolean | null;

export interface CidocCrmJsonObject {
  readonly [key: string]: CidocCrmJsonValue;
}

export type CidocCrmJsonValue =
  | CidocCrmJsonPrimitive
  | CidocCrmJsonObject
  | readonly CidocCrmJsonValue[];

export interface InSituVisitReport {
  readonly id: string;
  readonly createdAt: string;
  readonly createdBy: string;
  readonly projectId: string;
  readonly narrativeId: string;
  readonly inSituVisitRecordId: string;
}

export interface InSituVisitReportListItem extends InSituVisitReport {
  readonly code: string | null;
  readonly visitorName: string | null;
  readonly placeName: string | null;
  readonly visitBeginDate: string | null;
  readonly visitEndDate: string | null;
}

export interface InSituVisitReportNarrativeMeta {
  readonly resolvedNarrativeType: string;
  readonly resolutionSource: string;
  readonly targetLanguage: string;
  readonly creativityTemperature: number;
  readonly llmModel: string;
  readonly factsSnapshotId?: string | null;
  readonly promptVersion?: string | null;
  readonly modelResponseHash?: string | null;
  readonly validationConforms?: boolean | null;
  readonly validationFindings?: readonly InSituVisitNarrativeValidationFinding[];
}

export interface InSituVisitNarrativeValidationFinding {
  readonly code: string;
  readonly message: string;
  readonly evidence: string;
}

export interface InSituVisitNarrativeFactSnapshot {
  readonly id: string;
  readonly recordId: string;
  readonly payloadJson: string;
  readonly payloadHash: string;
  readonly builderVersion: string;
  readonly promptVersion: string;
  readonly createdAt: string;
}

export interface InSituVisitReportNarrative {
  readonly narrativeId: string;
  readonly recordId: string;
  readonly generatedAt: string;
  readonly meta: InSituVisitReportNarrativeMeta;
  readonly text: string;
  readonly factsSnapshot?: InSituVisitNarrativeFactSnapshot | null;
}

export interface InSituVisitReportAttachment {
  readonly id: string;
  readonly sourceId: string;
  readonly description: string;
  readonly reference: string;
  readonly position: number;
}

export interface InSituVisitReportEvidenceItem {
  readonly id: string;
  readonly sourceId: string;
  readonly description: string;
  readonly position: number;
  readonly attachments: readonly InSituVisitReportAttachment[];
}

export interface InSituVisitRecord {
  readonly id: string;
  readonly code: string;
  readonly visitBeginDate: string;
  readonly visitEndDate: string;
  readonly visitorName: string;
  readonly placeName: string;
  readonly generatedAt: string;
  readonly recordSchemaVersion?: number | null;
  readonly sourceProjectId?: string | null;
  readonly sourceProjectTitle?: string | null;
  readonly sourceProjectPurpose?: string | null;
  readonly plannedBeginDate?: string | null;
  readonly plannedEndDate?: string | null;
  readonly executionEvidenceType?: string | null;
  readonly executionOccurredAt?: string | null;
  readonly executionRecordedBy?: string | null;
  readonly executionEvidenceGaps?: readonly string[];
  readonly mappingVersion?: string | null;
  readonly crmVersion?: string | null;
  readonly requestedObjects: readonly InSituVisitReportEvidenceItem[];
  readonly inSituOccurrences: readonly InSituVisitReportEvidenceItem[];
  readonly inSituLogs: readonly InSituVisitReportEvidenceItem[];
  readonly inSituPublications: readonly InSituVisitReportEvidenceItem[];
}

export interface InSituVisitReportDetail extends InSituVisitReport {
  readonly narrative: InSituVisitReportNarrative | null;
  readonly record: InSituVisitRecord | null;
}

export type InSituVisitReportsQuery = PageQuery;
export type InSituVisitReportListPage = Page<InSituVisitReportListItem>;
// Kept until the list presentation migrates to the enriched row in REP-DETAIL-03.
export type InSituVisitReportsPage = Page<InSituVisitReport>;
