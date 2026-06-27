import { PermissionPrincipal } from '@core/auth/models/permission.model';
import { Page, PageQuery } from '@shared/models/page.model';
import { ObjectReference } from '@shared/models/object-reference.model';

import {
  IntendedUse,
  ProposalEventType,
  ProposalStatus,
  UseStatus,
  UseType,
} from '@shared/models/collection-use-status.model';

export type DocumentType = string;

export interface ProposalProjectSummary {
  readonly id: string;
  readonly referenceNumber: string;
  readonly title: string;
  readonly status: UseStatus;
}

export interface ProposalSummary {
  readonly id: string;
  // Proposal reference (VRP-YYYYMMDD-XXXX), distinct from the project's
  // collectionUseProject.referenceNumber (CUP-XXXXXXXX, empty until approval).
  readonly referenceNumber: string;
  // Proposal title (owned by the proposal). The linked project carries its own
  // collectionUseProject.title (empty until approval).
  readonly title: string;
  readonly status: ProposalStatus;
  readonly type: UseType;
  // Backend source for `type` — the service normalizes `intendedUse.useType`
  // into the flat `type` above.
  readonly intendedUse?: IntendedUse | null;
  // Requested use period (YYYY-MM-DD). Optional during contract rollout; the
  // backend now returns these on every proposal shape.
  readonly beginDate?: string;
  readonly endDate?: string;
  readonly requestedBy: PermissionPrincipal;
  readonly assignedTo: PermissionPrincipal | null;
  // Materialised only on approval — absent on proposals that have not yet been
  // approved, and the backend list may omit it. Always guard before dereferencing.
  readonly collectionUseProject?: ProposalProjectSummary;
  readonly submittedAt: string;
}

export interface RequestedObject {
  readonly id: string;
  readonly objectReference: ObjectReference;
  readonly category: string;
  readonly description: string;
  readonly requestedAt: string;
  readonly requestedBy: PermissionPrincipal;
}

export interface RequestedDocument {
  readonly id: string;
  readonly type: DocumentType;
  readonly description: string;
  readonly requestedAt: string;
  readonly requestedBy: PermissionPrincipal;
}

export interface Document {
  readonly id: string;
  readonly type: DocumentType;
  readonly fileName: string;
  readonly fileReference?: string;
  readonly submittedAt: string;
  readonly submittedBy: PermissionPrincipal;
}

export interface ProposalDetail extends ProposalSummary {
  readonly conversationId: string;
  readonly documents: readonly Document[];
  // Optional during migration; populated by mocks/contract and made required in the contract step.
  readonly requestedDocuments?: readonly RequestedDocument[];
  readonly requestedObjects: readonly RequestedObject[];
}

export interface ProposalEvent {
  readonly occurredAt: string;
  readonly type: ProposalEventType;
  readonly triggeredBy: PermissionPrincipal;
  readonly note: string | null;
}

export interface Message {
  readonly id: string;
  readonly sentAt: string;
  readonly sender: string;
  readonly recipient: string;
  readonly subject: string;
  readonly body: string;
  readonly attachments?: readonly MessageAttachment[];
}

export interface MessageAttachment {
  readonly documentId: string;
  readonly fileName: string;
}

export interface Conversation {
  readonly conversationId: string;
  readonly proposalId: string;
  readonly messages: readonly Message[];
  readonly page: number;
  readonly size: number;
  readonly totalElements: number;
  readonly totalPages: number;
}

export interface CreateProposalRequest {
  readonly title?: string | null;
  readonly intendedUse?: IntendedUse | null;
  readonly purpose?: string | null;
  readonly beginDate?: string | null;
  readonly endDate?: string | null;
  // Conversation seed (Business Rule 01 — every proposal opens with an email).
  // Proposal detail fields are optional during submission; the opening message
  // carries the researcher's first-contact request.
  readonly initialMessageRecipient?: string;
  readonly initialMessageSubject?: string;
  readonly initialMessageBody?: string;
}

// Contract: POST /proposals returns only the proposal summary + conversationId.
// No CollectionUseProject is created at submit — it is materialised on approval.
export interface CreateProposalResponse {
  readonly proposal: Omit<ProposalSummary, 'collectionUseProject'>;
  readonly conversationId: string;
}

export interface ProposalListQuery extends PageQuery {
  readonly status?: ProposalStatus | readonly ProposalStatus[];
  readonly type?: UseType;
  readonly requestedBy?: string;
  readonly assignedTo?: string;
  readonly dateFrom?: string;
  readonly dateTo?: string;
  readonly search?: string;
}

export interface ProposalDocumentsResponse {
  readonly proposalId: string;
  readonly documents: readonly Document[];
}

export interface ProposalEventsPage extends Page<ProposalEvent> {
  readonly proposalId: string;
}

// Contract returned by PATCH /proposals/{proposalId}. The endpoint returns a
// staff-action summary rather than a complete ProposalDetail and does not add
// an event, so lastEvent may be null.
export interface UpdateProposalResult {
  readonly id: string;
  readonly referenceNumber: string;
  readonly title: string | null;
  readonly status: ProposalStatus;
  readonly beginDate: string | null;
  readonly endDate: string | null;
  readonly lastEvent: ProposalEvent | null;
}

export interface SendMessageRequest {
  readonly recipient: string;
  readonly subject: string;
  readonly body: string;
  readonly documentIds?: readonly string[];
}
