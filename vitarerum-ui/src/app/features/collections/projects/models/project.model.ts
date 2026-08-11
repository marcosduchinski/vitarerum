import { GroupName } from '@core/auth/models/group-name.enum';
import { PermissionPrincipal } from '@core/auth/models/permission.model';
import { Page, PageQuery } from '@shared/models/page.model';
import { ObjectReference } from '@shared/models/object-reference.model';

import {
  MediaType,
  ProposalStatus,
  UseEventType,
  UseResult,
  UseStatus,
  UseType,
} from '@shared/models/collection-use-status.model';

export interface ProjectProposalSummary {
  readonly id: string;
  readonly status: ProposalStatus;
  readonly submittedAt?: string;
  readonly assignedTo?: PermissionPrincipal | null;
}

export interface CollectionUseProjectObject {
  readonly id: string;
  readonly inventoryNumber: string;
  readonly displayTitle: string | null;
  readonly objectName: string | null;
  readonly briefDescriptionSnapshot: string | null;
  readonly collectionId?: string | null;
  readonly collectionName?: string | null;
  readonly category: string;
  readonly description: string;
}

export interface CollectionUseProjectSummary {
  readonly id: string;
  readonly referenceNumber: string;
  readonly title: string;
  readonly purpose: string;
  readonly note?: string | null;
  readonly type: UseType;
  // Backend source for `type` — the service normalizes the bare `intendedUse`
  // use type into the flat `type` above.
  readonly intendedUse?: UseType | null;
  readonly status: UseStatus;
  // COMPLETED or CANCELLED once the project reaches a terminal outcome, otherwise null.
  readonly result?: UseResult | null;
  readonly beginDate: string;
  readonly endDate: string;
  // Populated only for staff callers; nullable and not yet set by any flow.
  readonly authorisedBy?: PermissionPrincipal | null;
  readonly authorisedAt?: string | null;
  readonly originProjectId?: string | null;
  readonly proposalId?: string | null;
  readonly requestedBy?: PermissionPrincipal | null;
  readonly proposal?: ProjectProposalSummary | null;
}

export interface Attachment {
  readonly fileReference: string;
  readonly fileName: string;
  readonly mediaType: MediaType;
  readonly uploadedAt: string;
  readonly attachmentDescription: string;
}

export interface ObjectAccessLog {
  readonly id: string;
  readonly referenceNumber: string;
  readonly projectId: string;
  readonly curator: PermissionPrincipal | null;
}

export interface ObjectOccurrenceLog {
  readonly id: string;
  readonly referenceNumber: string;
  readonly projectId: string;
  readonly curator: PermissionPrincipal | null;
}

// The publication log records publications/outputs derived from a project. Unlike
// the object access/occurrence logs it has no conclusion — only an informational
// `curator` (the staff member related to the project, snapshotted from the
// proposal's assignee).
export interface PublicationLog {
  readonly id: string;
  readonly referenceNumber: string;
  readonly projectId: string;
  readonly curator: PermissionPrincipal | null;
}

export interface PublicationLogEntry {
  readonly id: string;
  readonly collectionUseObjectId?: string | null;
  readonly addedAt: string;
  readonly addedBy: PermissionPrincipal;
  readonly note: string;
  readonly attachments: readonly Attachment[];
}

export interface ObjectLogEntry {
  readonly id: string;
  readonly collectionUseObjectId: string;
  readonly objectReference: ObjectReference;
  readonly numberOfObjects: number;
  readonly addedAt: string;
  readonly addedBy: PermissionPrincipal;
  readonly observations: string | null;
  readonly requestedObjectId?: string | null;
  readonly attachments: readonly Attachment[];
}

export interface ObjectOccurrenceEntry {
  readonly id: string;
  readonly collectionUseObjectId: string;
  readonly objectReference: ObjectReference;
  readonly numberOfObjects: number;
  readonly occurrenceDate: string;
  readonly location: string;
  readonly reportedBy: PermissionPrincipal;
  readonly detailedDescription: string;
  readonly testimonial: string | null;
  readonly requestedObjectId?: string | null;
  readonly attachments: readonly Attachment[];
}

export interface ProjectActionPermissions {
  readonly canStart: boolean;
  readonly canComplete: boolean;
  readonly canCancel: boolean;
  readonly canOpenLog: boolean;
  readonly canCreateObjectLogEntry: boolean;
  readonly canCreateOccurrenceEntry: boolean;
}

export interface ProjectTodoItem {
  readonly id: string;
  readonly projectId: string;
  readonly text: string;
  readonly completed: boolean;
  readonly createdAt: string;
  readonly updatedAt: string;
  readonly completedAt: string | null;
  readonly position: number;
}

export interface ProjectTodoItemsResponse {
  readonly projectId: string;
  readonly items: readonly ProjectTodoItem[];
}

export interface CreateProjectTodoItemRequest {
  readonly text: string;
}

export interface UpdateProjectTodoItemRequest {
  readonly text?: string;
  readonly position?: number;
}

export interface ProjectStaffProposalContext {
  readonly id: string;
  readonly referenceNumber: string;
  readonly title: string;
  readonly status: ProposalStatus;
  readonly submittedAt: string;
  readonly submittedBy: PermissionPrincipal;
  readonly assignedTo: PermissionPrincipal | null;
}

export interface ProjectRequestedObjectContext {
  readonly id: string;
  readonly objectReference: ObjectReference;
  readonly category: string;
  readonly description: string;
  readonly requestedAt: string;
  readonly requestedBy: PermissionPrincipal;
}

export interface ProjectRequestedDocumentContext {
  readonly id: string;
  readonly type: string;
  readonly description: string;
  readonly requestedAt: string;
  readonly requestedBy: PermissionPrincipal;
}

export interface ProjectDocumentContext {
  readonly id: string;
  readonly type: string;
  readonly fileName: string;
  readonly fileReference?: string;
  readonly submittedAt: string;
  readonly submittedBy: PermissionPrincipal;
}

export interface ProjectConversationSummary {
  readonly conversationId: string;
  readonly totalMessages: number;
  readonly lastMessageAt: string | null;
  readonly lastMessageBy: PermissionPrincipal | null;
}

export interface ProjectLogSummary {
  readonly accessLog: ObjectAccessLog | null;
  readonly occurrenceLog: ObjectOccurrenceLog | null;
  readonly objectLogEntryCount: number;
  readonly occurrenceEntryCount: number;
  readonly attachmentCount: number;
}

export interface ProjectDirectionContext {
  readonly latestQuestion: string | null;
  readonly latestClarification: string | null;
  readonly referredAt: string | null;
  readonly clarifiedAt: string | null;
}

export interface ProjectStaffContext {
  readonly viewerGroup: Exclude<GroupName, 'EXTERNAL'>;
  readonly proposal: ProjectStaffProposalContext;
  readonly requestedObjects: readonly ProjectRequestedObjectContext[];
  readonly requestedDocuments: readonly ProjectRequestedDocumentContext[];
  readonly documents: readonly ProjectDocumentContext[];
  readonly conversationSummary: ProjectConversationSummary | null;
  readonly logSummary: ProjectLogSummary;
  readonly directionContext: ProjectDirectionContext | null;
}

export interface CollectionUseProjectDetail extends CollectionUseProjectSummary {
  readonly objects?: readonly CollectionUseProjectObject[];
  readonly actions?: ProjectActionPermissions;
  readonly staffContext?: ProjectStaffContext | null;
}

export interface UseEvent {
  readonly occurredAt: string;
  readonly type: UseEventType;
  readonly triggeredBy: PermissionPrincipal;
  readonly note: string | null;
}

export interface ProjectListQuery extends PageQuery {
  readonly status?: UseStatus;
  readonly type?: UseType;
  readonly dateFrom?: string;
  readonly dateTo?: string;
  readonly search?: string;
  // `requestedBy` is an honored server-side filter: staff may scope to any
  // requester's permissionId (e.g. their own for a "my projects" view), while
  // non-staff callers are always auto-scoped to their own permissionId.
  readonly requestedBy?: string;
  readonly originProjectId?: string;
  // `assignedTo` is not implemented server-side; stripped before the request and
  // honoured only by the mock.
  readonly assignedTo?: string;
}

export interface ObjectLogEntriesQuery extends PageQuery {
  readonly addedBy?: string;
}

export interface ObjectOccurrenceEntriesQuery extends PageQuery {
  readonly reportedBy?: string;
}

export interface PublicationEntriesQuery extends PageQuery {
  readonly addedBy?: string;
}

export interface ProjectEventsQuery extends PageQuery {
  readonly type?: UseEventType;
}

export interface ObjectLogEntriesPage extends Page<ObjectLogEntry> {
  readonly projectId: string;
  readonly accessLog: ObjectAccessLog | null;
}

export interface ObjectOccurrenceEntriesPage extends Page<ObjectOccurrenceEntry> {
  readonly projectId: string;
  readonly occurrenceLog: ObjectOccurrenceLog | null;
}

export interface PublicationEntriesPage extends Page<PublicationLogEntry> {
  readonly projectId: string;
  readonly publicationLog: PublicationLog | null;
}

export interface ProjectEventsPage extends Page<UseEvent> {
  readonly projectId: string;
}

export interface NoteRequest {
  readonly note: string;
}

export interface ReasonRequest {
  readonly reason: string;
}

export interface UpdateProjectRequest {
  readonly title?: string | null;
  readonly purpose?: string | null;
  readonly beginDate?: string | null;
  readonly endDate?: string | null;
}

export interface ProjectObjectSnapshotInput {
  readonly inventoryNumber: string;
  readonly displayTitle: string;
  readonly objectName: string;
  readonly briefDescriptionSnapshot?: string | null;
  readonly collectionId?: string | null;
  readonly collectionName?: string | null;
  readonly category?: string;
  readonly description?: string;
}

export interface AddProjectObjectsRequest {
  readonly objects: readonly ProjectObjectSnapshotInput[];
}

export interface CreateFollowUpProjectRequest {
  readonly beginDate: string;
  readonly endDate: string;
  readonly objectIds: readonly string[];
  readonly title?: string | null;
  readonly purpose?: string | null;
  readonly note?: string | null;
}

export interface RemoveProjectObjectRequest {
  readonly confirmCascade: boolean;
  readonly reason: string;
}

export interface ProjectObjectDependencySummary {
  readonly accessLogEntries: number;
  readonly occurrenceEntries: number;
  readonly publicationEntries: number;
  readonly attachments: number;
}

export interface CreateObjectLogEntryRequest {
  readonly collectionUseObjectId: string;
  readonly numberOfObjects: number;
  readonly observations?: string;
}

export interface UpdateObjectLogEntryRequest {
  readonly addedAt?: string;
  readonly numberOfObjects?: number;
  readonly observations?: string | null;
}

export interface CreateObjectOccurrenceEntryRequest {
  readonly collectionUseObjectId: string;
  readonly numberOfObjects: number;
  readonly occurrenceDate: string;
  readonly location: string;
  readonly detailedDescription: string;
  readonly testimonial?: string;
}

export interface UpdateObjectOccurrenceEntryRequest {
  readonly numberOfObjects?: number;
  readonly occurrenceDate?: string;
  readonly location?: string;
  readonly detailedDescription?: string;
  readonly testimonial?: string | null;
}
